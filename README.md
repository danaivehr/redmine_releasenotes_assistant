# Redmine Release Assistant

A simple Python script that fetches issue data from a Redmine instance and automatically generates release notes in natural language.

## Features
- Fetches issues from a Redmine instance via API
- Groups issues based on relations, categories and trackers
- Generates structured release notes in natural language with OpenAI API 

## Installation
1. Clone the repository:
   ```sh
   git clone https://github.com/danaivehr/redmine_releasenotes_assistant.git
   cd redmine-release-notes
   ```
2. Install dependencies:
   ```sh
   pip install openai requests
   ```

## Configuration
Copy a `settings.sample.json` to a new json file and modify values:

- `redmine_host`: your Redmine instance to fetch issues
- `api_key`: Redmine API key for authentification
- `project_id`: Redmine project identifier (that one from a link to a project)
- `version_name`: Redmine fixed version name 
- `main_tracker`: Redmine tracker name, which will lead in the release notes for related issues
- `category_other`: default category name for issues without a category
- `include_parent_in_relations`: to consider parent-child link as a relation or not
- `gpt_api_key`: OpenAI API key for authentification
- `gpt_model`: gpt model name to use

Create text instructions for GPT how to deal with input and create a note for related issues, then store them to a txt file.

## Usage
Run the script with:
```sh
python redmine_releasenotes_assistant.py -c settings.json -g -m ./instructions_for_gpt.txt
```

This will do:
- Fetch of all issues with comments for project and version provided in settings and store issues to file named `issue_data_{version_id}_{version_name}.json`.
- Analize relations and categories, group issues by relations, depersonalize authors and store the result to file named `release_notes_source_{version_id}_{version_name}.json`.
- Pass each group of related issues including descriprion and comment history to OpenAI with instructions to get a natural language note for release notes.
- Create release notes in textile formatting for publishing to Redmine wiki. 

Please check `--help` to see other possible options and usecases:

```
options:
  -h, --help            show this help message and exit
  -c, --config CONFIG   config filename
  -d, --depersconfig DEPERSCONFIG
                        deprsonalization config filename
  -i, --issuedata ISSUEDATA
                        provide issue data json to skip fetching
  -n, --notessource NOTESSOURCE
                        provide issue data json to skip fetching and release notes source generation
  -g, --usegpt          use chatGPT to create natural language notes
  -m, --messageforgpt MESSAGEFORGPT
                        instructions file how to compose a note for chatGPT
  -l, --limitforgpt LIMITFORGPT
                        limit notes count to compose with chatGPT (for thrifty instructions testing)
```

### Release notes example

```
h2. New in version 1.2.3

{{>toc}}

h3. Usability

* #1132, #1126 Some natural language description created for this group.
* #2134, #2123, #2122 Another natural language description created for this group.

h3. Security

* #1130, #1124 Some natural language description created for this group.
* #2131 Another natural language description created for this group.

```

## Requirements
- Python 3.7+
- `requests` library
- `openai` library

## License
This project is licensed under the GPL 3.0 License.
