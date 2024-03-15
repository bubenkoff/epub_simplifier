# EPUB Simplifier

![Test](https://github.com/bubenkoff/epub-simplifier/actions/workflows/test.yml/badge.svg)
[![PyPI Version](https://img.shields.io/pypi/v/epub-simplifier.svg)
](https://pypi.python.org/pypi/epub-simplifier)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/epub-simplifier)
](https://pypi.python.org/pypi/epub-simplifier)
[![Coverage](https://img.shields.io/coveralls/bubenkoff/epub-simplifier/main.svg)
](https://coveralls.io/r/bubenkoff/epub-simplifier)

## Description
EPUB Simplifier is a command-line tool designed to convert text within EPUB files into a simplified language at a selected proficiency level. This tool aims to make literature more accessible to language learners by simplifying complex language structures and vocabulary.

> [!WARNING]
> It uses OpenAI API and requires an API key to work, which is not provided with the package. It can also be quite expensive to use, depending on the size of the book.

## Motivation
The idea for this tool was inspired by the need to make literature more accessible to language learners. Many language learners struggle to read books in their target language due to the complexity of the language used in literature. This tool addresses this issue by simplifying the language used in books to make them more accessible to language learners at different proficiency levels.

In particular, for the Dutch language, there is a lack of literature in accessible language in electronic format. Having the text on an e-book allows using built-in dictionaries and other tools to help comprehensively understand the text.

## Installation
To install EPUB Simplifier, follow these steps:

``
pip install epub-simplifier
``

## Usage
After installation, you can use the EPUB Simplifier tool directly from your command line. The basic command structure is as follows:

``
export OPENAI_API_KEY=your_api_key
``

Optionally, set the organization ID if you have one:

``
export OPENAI_ORG_ID=your_org_id
``

Run the command:

``
epub-simplify --help
``

## Example Command

``
epub-simplify original_book.epub simplified_book.epub Dutch B1
``

This command will read `original_book.epub`, simplify its contents, and save the result as `simplified_book.epub`.

## Requirements
The dependencies will be installed automatically during the package installation process.

## Feedback and Contributions
Your feedback and contributions are welcome! If you encounter any issues or have suggestions for improvements, please feel free to open an issue on the GitHub repository or submit a pull request with your changes.

## License
MIT 
