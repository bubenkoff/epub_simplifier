from bs4 import BeautifulSoup
from openai.types.chat.chat_completion import (
    ChatCompletion,
    Choice,
    ChatCompletionMessage,
    CompletionUsage,
)
import pytest
from epub_simplifier.simplifier import main
from ebooklib import epub
import ebooklib
from markdownify import markdownify as md


@pytest.mark.parametrize("dry_run", [True, False])
def test_main(dry_run, mocker, tmp_path):
    async def create_completion(**params):
        user_input = params["messages"][-1]["content"]
        simplified_text = user_input.replace("complicated", "simplified")
        return ChatCompletion(
            id="completion-123",
            created=1630000000,
            model="gpt-4-turbo-preview",
            object="chat.completion",
            choices=[
                Choice(
                    index=0,
                    finish_reason="stop",
                    message=ChatCompletionMessage(
                        content=simplified_text,
                        role="assistant",
                    ),
                )
            ],
            usage=CompletionUsage(
                completion_tokens=100,
                prompt_tokens=100,
                total_tokens=200,
            ),
        )

    patched = mocker.patch(
        # api_call is from slow.py but imported to main.py
        "epub_simplifier.simplifier.client.chat.completions.create",
        side_effect=create_completion,
    )
    input_path = "./tests/data/book.epub"
    output_path = str(tmp_path / "simplified_book.epub")
    mocker.patch(
        "sys.argv",
        [
            "epub-simplify",
            input_path,
            output_path,
            "English",
            "B1",
            "--yes",
            "--max-tokens=30",
            *(["--dry-run"] if dry_run else []),
        ],
    )
    main()
    # read the original book and check that it contains the expected text
    original_book = epub.read_epub(input_path, {"ignore_ncx": True})
    original_documents = list(original_book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    original_title = original_book.get_metadata("DC", "title")[0][0]
    assert len(original_documents) == 1
    original_content = original_documents[0].get_content()
    original_soup = BeautifulSoup(original_content, "html.parser")
    original_text = md(str(original_soup.body)).strip()
    assert original_text == """complicated text 1


complicated text 2"""

    if dry_run:
        # check that the output file is not created in dry-run mode
        assert not (tmp_path / "simplified_book.epub").exists()
        # and mock of the api is not called
        assert not patched.called
        return
    assert patched.call_count == 2
    # read the simplified book and check that it contains the expected text
    simplified_book = epub.read_epub(output_path, {"ignore_ncx": True})
    simplified_documents = list(
        simplified_book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
    )
    simplified_title = simplified_book.get_metadata("DC", "title")[0][0]

    assert len(original_documents) == len(simplified_documents)
    assert original_title == simplified_title
    simplified_content = simplified_documents[0].get_content()
    simplified_soup = BeautifulSoup(simplified_content, "html.parser")
    simplified_text = md(str(simplified_soup.body)).strip()
    assert simplified_text == """simplified text 1


simplified text 2"""
