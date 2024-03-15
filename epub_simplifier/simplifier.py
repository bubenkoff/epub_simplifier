import argparse
import logging
import asyncio
import os
import ebooklib
from ebooklib import epub
from markdownify import markdownify as md
import tiktoken
from importlib.metadata import version

from bs4 import BeautifulSoup
from openai import AsyncOpenAI as OpenAI
from progress.bar import Bar
import markdown2
from tenacity import (
    retry,
    retry_if_exception_type,
    # stop_after_attempt,
    wait_random_exponential,
    before_log,
)  # for exponential backoff

# require environment variables
if "OPENAI_API_KEY" not in os.environ:
    raise ValueError(
        "OpenAI API key is not set. Please set the OPENAI_API_KEY environment variable."
    )
client = OpenAI()
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
separator = "\n\n"

wait_arguments = {
    "retry": retry_if_exception_type(IOError),
    "wait": wait_random_exponential(min=1),
    "before": before_log(logger, logging.DEBUG),
    # "stop": stop_after_attempt(6),
}


def chunkify_text(text, separator, max_tokens):
    """
    Split text into chunks of max_tokens length.
    """
    chunks = []
    words = text.split(separator)
    chunk = ""
    for word in words:
        if len(chunk) + len(word) < max_tokens:
            chunk += separator + word
        else:
            chunks.append(chunk.strip())
            chunk = word
    chunks.append(chunk.strip())
    return chunks


def dechunkify_text(chunks, separator):
    """
    Combine chunks of text into a single text.
    """
    usage = {
        "input": sum((usage["input"] for (_, usage) in chunks)),
        "output": sum((usage["output"] for (_, usage) in chunks)),
    }
    return separator.join((chunk for (chunk, _) in chunks)), usage


@retry(**wait_arguments)
async def simplify_chapter(title, text, language, level, max_tokens, model, dry_run):
    """
    Simplify the text to a selected level using the latest OpenAI package.
    """
    result = []
    chunks = chunkify_text(text, separator, max_tokens)
    instructions = [
        {
            "role": "system",
            "content": f"You are a highly knowledgeable {language} teacher",
        },
        {
            "role": "system",
            "content": f"Your student is a {level} student who wants to read {language} literature",
        },
    ]
    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(
                process_chunk(title, chunk, language, instructions, model, dry_run)
            )
            for chunk in chunks
        ]
    result = [task.result() for task in tasks]
    text, usage = dechunkify_text(result, separator)
    logger.debug(f"\nSimplified text: {text}, usage: {usage}")
    # try:
    #     response = await client.chat.completions.create(
    #         model=model,  # Choose the best model for your needs. 'gpt-3.5-turbo' is suggested for efficiency and cost.
    #         messages=[
    #             *instructions,
    #             {
    #                 "role": "system",
    #                 "content": f"Given chapter from the {language} book {title} in Markdown format was previously rephrased "
    #                     "by you, chunk by chunk, to the student's level keeping the meaning, length, tone, humor etc intact",
    #             },
    #             {
    #                 "role": "system",
    #                 "content": "Now, please review the chunks combined into a single text and make any necessary "
    #                    "adjustments to ensure the text is coherent and consistent, but do not shorten the text",
    #             },
    #             {
    #                 "role": "user",
    #                 "content": text,
    #             },
    #         ],
    #     )
    #     # Extracting and returning the completion text
    #     choice = response.choices[0]
    #     if choice.finish_reason == "length":
    #         logger.warning("Response was truncated.")
    #     text = choice.message.content.strip()
    # except Exception as e:
    #     logger.error(f"Error during API call: {e}")
    return text, usage


@retry(**wait_arguments)
async def process_chunk(title, text, language, instructions, model, dry_run):
    logger.debug(f"\nProcessing chunk: {model}, dry_run: {dry_run}")
    # sleep for a while
    if dry_run:
        # calculate the number of tokens
        if model.startswith("gpt-4"):
            # turbo not yet supported
            model = "gpt-4"
        enc = tiktoken.encoding_for_model(model)
        tokens = enc.encode(text)
        cnt = len(tokens)
        # sleep for a while
        await asyncio.sleep(0.1)
        # for input and output
        return text, {"input": cnt, "output": cnt}
    response = await client.chat.completions.create(
        model=model,  # Choose the best model for your needs. 'gpt-3.5-turbo' is suggested for efficiency and cost.
        messages=[
            *instructions,
            {
                "role": "system",
                "content": f"Rephrase the chunk of the chapter from the {language} book {title} in Markdown format to the "
                "student's level keeping the meaning, length, tone, humor etc intact, but do not shorten the text.",
            },
            {
                "role": "user",
                "content": text,
            },
        ],
    )
    # Extracting and returning the completion text
    choice = response.choices[0]
    usage = {
        "input": response.usage.prompt_tokens,
        "output": response.usage.completion_tokens,
    }
    logger.debug(f"\nResponse usage: {usage}")
    if choice.finish_reason == "length":
        logger.warning("\nResponse was truncated. Decrease max_tokens.")
    return choice.message.content.strip(), usage


async def show_progress(result_queue, count):
    """
    Show progress bar for the simplification process.
    """
    with Bar("Processing", max=count) as bar:
        while True:
            # check if the queue size is count
            try:
                size = result_queue.qsize()
            except (EOFError, BrokenPipeError):
                size = count
            bar.goto(size)
            if size == count:
                break
            # wait for a while
            await asyncio.sleep(0.1)
        bar.finish()


async def simplify_epub_book(
    input_path,
    output_path,
    language,
    level,
    max_documents=None,
    save_html=False,
    only_documents=None,
    max_tokens=None,
    dry_run=False,
    model=None,
    pricing_input=None,
    pricing_output=None,
):
    """
    Extract text from an EPUB file, simplify the text to given level, and create a new EPUB.
    """
    # get containing directory
    containing_directory = os.path.dirname(input_path)
    # get a folder name for the html to save
    folder_name = os.path.basename(input_path).split(".")[0]
    html_path = os.path.join(containing_directory, folder_name)
    if save_html and not os.path.exists(html_path):
        os.makedirs(html_path)
    book = epub.read_epub(input_path, {"ignore_ncx": True})
    title = book.get_metadata("DC", "title")[0][0]
    simplified_book = book
    # Process each item in the EPUB
    index = 1
    documents = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    count = len(documents)
    if only_documents:
        only_documents = set(only_documents)
    documents = [
        document
        for index, document in enumerate(documents)
        if not only_documents or index in only_documents
    ]
    if max_documents:
        documents = documents[:max_documents]
    count = len(documents)
    # process documents in parallel using multiprocessing
    usage = {
        "input": 0,
        "output": 0,
    }
    result_queue = asyncio.Queue()
    # start a thread to show progress
    asyncio.create_task(show_progress(result_queue, count))
    async with asyncio.TaskGroup() as group:
        # create and issue tasks
        tasks = [
            group.create_task(
                process_document(
                    language,
                    level,
                    save_html,
                    max_tokens,
                    html_path,
                    title,
                    index,
                    count,
                    item,
                    result_queue,
                    model,
                    dry_run,
                )
            )
            for index, item in enumerate(documents)
        ]

    for index, (content, _usage) in enumerate(task.result() for task in tasks):
        usage["input"] += _usage["input"]
        usage["output"] += _usage["output"]
        if not dry_run:
            documents[index].set_content(content.encode("utf-8"))
    if not dry_run:
        # Write the simplified book to an EPUB file
        epub.write_epub(output_path, simplified_book, {})
        logger.info("\nBook simplification completed.")
    cost = usage["input"] * pricing_input + usage["output"] * pricing_output
    logger.info(
        f"\nTotal tokens input: {usage['input']}, output: {usage['output']}{dry_run and ' (estimated)' or ''}"
        f"\nCost: {cost:.2f} USD {dry_run and ' (estimated)' or ''}."
    )


async def process_document(
    language,
    level,
    save_html,
    max_tokens,
    html_path,
    title,
    index,
    count,
    item,
    result_queue,
    model,
    dry_run,
):
    """Process a single document in the EPUB file."""
    # sleep for a while
    content = item.get_content().decode("utf-8")
    simplified_content = content
    logger.debug(f"\nProcessing item: {index}")
    soup = BeautifulSoup(content, "html.parser")
    # text = soup.get_text()
    text = md(str(soup.body))
    if save_html:
        with open(os.path.join(html_path, f"{index}_input.html"), "w") as f:
            f.write(content)
        with open(os.path.join(html_path, f"{index}_input.md"), "w") as f:
            f.write(text)
    simplified_text, usage = await simplify_chapter(
        title, text, language, level, max_tokens, model, dry_run
    )
    if simplified_text:
        logger.debug(f"\nSimplified: {index}")
        simplified_content = markdown2.markdown(simplified_text)
        soup.body.clear()
        soup.body.append(BeautifulSoup(simplified_content, "html.parser"))
        simplified_content = str(soup)
        if save_html:
            with open(os.path.join(html_path, f"{index}_output.html"), "w") as f:
                f.write(simplified_content)
            with open(os.path.join(html_path, f"{index}_output.md"), "w") as f:
                f.write(simplified_text)
        # simplified_book.add_item(item)
    logger.debug(f"\nProcessed {index} document of {count}.")
    await result_queue.put(index)
    return simplified_content, usage


def main():
    """Entry point for the command line interface."""
    parser = argparse.ArgumentParser(
        description="Simplify text in EPUB files to selected language level."
    )
    parser.add_argument("input_path", type=str, help="Path to the original EPUB file.")
    parser.add_argument(
        "output_path", type=str, help="Path to save the simplified EPUB file."
    )
    parser.add_argument("language", type=str, help="Language to simplify.")
    parser.add_argument("level", type=str, help="Language level to simplify to.")
    # max documents to process
    parser.add_argument("--max-documents", type=int, help="Max documents to process.")
    # save html documents to disk
    parser.add_argument(
        "--save-html", action="store_true", help="Save HTML documents to disk."
    )
    # only process the selected documents, can be used for testing
    parser.add_argument(
        "--only-documents",
        type=lambda t: [int(s.strip()) for s in t.split(",")],
        help="Only process the selected documents. Comma-separated list of document numbers.",
    )
    # max tokens for the API call
    parser.add_argument(
        "--max-tokens",
        type=int,
        help="Max tokens for the API call. It's a total magic to select a proper value due to the OpenAI model behavior.",
        default=13000,
    )
    # dry run
    parser.add_argument(
        "--dry-run", action="store_true", help="Run without making any changes."
    )
    # model
    parser.add_argument(
        "--model",
        type=str,
        help="OpenAI model to use. Default is gpt-4-turbo-preview.",
        default="gpt-4-turbo-preview",
    )
    # price per input token
    parser.add_argument(
        "--pricing-input",
        type=float,
        help="Price per input token in USD",
        default=10 / (10**6),
    )
    # price per output token
    parser.add_argument(
        "--pricing-output",
        type=float,
        help="Price per output token in USD",
        default=30 / (10**6),
    )
    # answer yes to all questions
    parser.add_argument(
        "--yes", action="store_true", help="Answer yes to all questions."
    )
    # log level
    parser.add_argument(
        "--log-level",
        type=str,
        help="Log level. Default is INFO.",
        default="INFO",
    )
    # version
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {version('epub-simplifier')}"
    )

    args = parser.parse_args()
    # set log level
    logger.setLevel(args.log_level)
    # check for input and output paths not being the same
    if args.input_path == args.output_path:
        raise ValueError("Input and output paths cannot be the same.")

    for dry_run in args.dry_run and (True,) or (args.yes and (False,) or (True, False)):
        asyncio.run(
            simplify_epub_book(
                args.input_path,
                args.output_path,
                args.language,
                args.level,
                max_documents=args.max_documents,
                save_html=args.save_html,
                only_documents=args.only_documents,
                max_tokens=args.max_tokens,
                dry_run=dry_run,
                model=args.model,
                pricing_input=args.pricing_input,
                pricing_output=args.pricing_output,
            )
        )
        if not args.dry_run and dry_run:
            # confirm to proceed despite the cost
            proceed = input("Do you want to proceed despite the cost? (y/n): ")
            if proceed.lower() != "y":
                logger.info("Exiting.")
                break
