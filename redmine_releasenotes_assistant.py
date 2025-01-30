import requests
import json
import argparse
import sys
from functools import reduce
from openai import OpenAI

class RedmineReleaseAssistant:
    
    def __init__(self, settings):

        self.redmine_host = settings['redmine_host']
        self.project_id = settings['project_id']
        self.version_name = settings['version_name']
        self.version_id = None
        self.issues = []
        self.issues_data = {}
        self.release_notes = {}
        self.notes_title = settings['notes_title']
        self.main_tracker = settings['main_tracker']
        self.category_other = settings['category_other']
        self.include_parent_in_relations = settings['include_parent_in_relations']
        self.depers_settings = settings['depers_settings']
        self.gpt_how_to_compose_note = settings['gpt_how_to_compose_note']
        self.gpt_model = settings['gpt_model']
        self.gpt_api_key = settings['gpt_api_key']

        self.session = requests.Session()
        self.session.headers.update(
            {'X-Redmine-API-Key': settings['api_key']}
        )

        self.set_version_id()
        self.fetch_issue_list()

    def set_version_id(self):

        response = self.session.get(
            f'{self.redmine_host}/projects/{self.project_id}/versions.json'
        )

        versions = dict(response.json())['versions']
        versions_by_name = list(filter(
            lambda version: version['name'] == self.version_name,
            versions
        ))
        
        self.version_id = None if versions_by_name == [] \
            else int(versions_by_name[0]['id'])
    
    def fetch_issue_list(self):

        query = {
            'fixed_version_id': self.version_id,
            'status_id': '*',
            'offset': 0
        }
        
        offset = 0
        total = 1
        issues = []

        while offset < total:

            response = self.session.get(
                f'{self.redmine_host}/issues.json',
                params = query
            )

            portion = dict(response.json())
            issues += portion['issues']
            offset += portion['limit']
            query['offset'] = offset
            total = portion['total_count']

        self.issues = list(map(lambda issue: issue['id'], issues))

    def fetch_issues_data(self):

        def get_issue_data(issue_id):

            def issue_shrinked():
                
                issue = {}
                details = issue_details['issue']

                issue['id'] = details['id']
                issue['tracker'] = details['tracker']['name']
                issue['status'] = details['status']['name']
                issue['priority'] = details['priority']['name']

                issue['category'] = details['category']['name'] if 'category' in details else None

                issue['subject'] = details['subject']
                issue['description'] = details['description']

                issue['parent'] = details['parent']['id'] if 'parent' in details else None

                issue['relations'] = []
                issue['children'] = []
                issue['comments'] = []
                issue['pics'] = []

                for journal in details['journals']:
                    
                    if not journal['notes'] in ['', None]:
                        
                        issue['comments'].append({
                            'text' : journal['notes'],
                            'author' : journal['user']['name'],
                            'date' : journal['created_on'],
                        })

                for attachment in details['attachments']:

                    if attachment['content_type'] == 'image/png':
                        
                        issue['pics'].append({
                            'filename' : attachment['filename'],
                            #'content_url' : attachment['content_url'],
                        })

                if 'relations' in details:
                    
                    for relation in details['relations']:
                        
                        issue['relations'].append({
                            'related_id' : relation['issue_id'],
                            'relation_type' : relation['relation_type'],
                        })

                if 'children' in details:
                    
                    for child in details['children']:
                        
                        issue['children'].append({
                            'child_id' : child['id'],
                        })

                return issue

            query = {
                'include' : 'journals,attachments,relations,children'
            }

            response = self.session.get(
                f'{self.redmine_host}/issues/{issue_id}.json',
                params = query
            )

            issue_content = response.content.decode('utf8')
            issue_details = json.loads(issue_content)
            
            return issue_shrinked()
 
        self.issues_data = dict(map(
            lambda issue_id: (issue_id, get_issue_data(issue_id)),
            self.issues
        ))

    def depersonalize(self):
        
        settings = self.depers_settings
        author_number = 0

        for issue_id, issue_data in self.issues_data.items():
            
            for comment in issue_data['comments']:
                
                if not comment['author'] in settings:
                    author_number += 1
                    settings[comment['author']] = f'Author {author_number}'
                
                comment['author'] = settings[comment['author']]

        if author_number > 0:
            print(f'{author_number} author{'' if author_number % 10 == 1 else 's'} \
                added to depersonalization settings.')

    def create_release_notes(self):

        def get_category(issue_group):

            if len(issue_group) == 0:
                return None
            
            issues_data = self.issues_data

            issues = list(issue_group)

            issues.sort(
                key = lambda issue_id :
                    2 if issues_data[issue_id]['tracker'] == self.main_tracker \
                        else 1
                    + 1 if not issues_data[issue_id]['category'] \
                            in [None, self.category_other] \
                        else -1,
                    # Main tracker with category == 3
                    # Other tracker with category == 2
                    # The rest doesn't matter (1 or 0)
                reverse = True
            )
        
            category = issues_data[issues[0]]['category']

            return (category if not category == None else self.category_other)

        def get_groups_by_relations():

            issues_data = self.issues_data
            include_parent = self.include_parent_in_relations
            issues_from_other_versions = []
            issue_groups = []

            issues = set(issues_data)

            for issue_id, issue_data in issues_data.items():
                
                related_issues = set()
                related_issues.add(issue_id)

                if include_parent and not issue_data['parent'] == None:
                    related_issues.add(issue_data['parent'])

                for related in issue_data['relations']:
                    related_issues.add(related['related_id'])

                if include_parent:
                    for child in issue_data['children']:
                        related_issues.add(child['child_id'])
                
                issue_groups.append(related_issues.intersection(issues))
                issues_from_other_versions += related_issues.difference(issues)

            issues_from_other_versions = set(issues_from_other_versions)
            issues_from_other_versions = list(map(
                lambda issue_id: str(issue_id), issues_from_other_versions
            ))

            print(
                f'Please check related issues from other versions:',
                ','.join(issues_from_other_versions)
            )
            
            groups_by_relations = []

            while len(issue_groups) > 0:
                
                collected = False
                absorber_group = issue_groups[0]

                while not collected:

                    related_groups = list(filter(
                        lambda issue_group :
                            len(absorber_group.intersection(issue_group)) > 0,
                        issue_groups
                    ))

                    issue_groups = \
                        [group for group in issue_groups if not group in related_groups]
                    
                    collected_group = reduce(
                        lambda group1, group2: group1.union(group2),
                        related_groups,
                        absorber_group
                    )

                    if len(absorber_group) == len(collected_group):
                        collected = True
                    else:
                        absorber_group = collected_group

                groups_by_relations.append(list(collected_group))

            return groups_by_relations

        def issue_data_for_note(issue_data):
            
            keys = [
                'id',
                'tracker',
                'subject',
                'description',
                'comments'
            ]

            return dict(map(lambda key : (key, issue_data[key]), keys))

        release_notes = {}
        issues_data = self.issues_data

        issue_groups_by_relations = get_groups_by_relations()
        
        for issue_group in issue_groups_by_relations:
            
            category = get_category(issue_group)

            if not category in release_notes:
                release_notes[category] = []
            
            issue_group.sort(
                key = lambda issue_id: 
                    issues_data[issue_id]['tracker'] == self.main_tracker,
                reverse = True
            )

            note = dict(map(
                lambda issue_id: (
                    issue_id, issue_data_for_note(issues_data[issue_id])
                ),
                issue_group
            ))
            
            release_notes[category].append(note)

        # Restructure for better chatGPT experiance
        self.release_notes = {'sections': []}

        for section in release_notes:

            new_section = {
                'section_name': section,
                'section_notes': []
            }

            for note in release_notes[section]:
                
                new_note = {
                    'note_text': None,
                    'related_issues': list(map(lambda issue: note[issue], note))
                }

                new_section['section_notes'].append(new_note)

            self.release_notes['sections'].append(new_section)

    def release_notes_as_textile(self):

        release_notes = ''        
        release_notes += 'h2. %s %s\n\n{{>toc}}\n\n' % (self.notes_title, self.version_name)

        for section in self.release_notes['sections']:

            release_notes += 'h3. %s\n\n' % section['section_name']

            for note in section['section_notes']:

                ids = ', '.join(list(map(
                    lambda issue: f'#{issue['id']}', note['related_issues']
                )))
                
                # Temporary begore chat success
                #subjects = '; '.join(list(map(lambda issue : topic[issue]['subject'], topic)))
                
                if note['note_text'] == None:
                    note_text = '; '.join(list(map(
                        lambda issue: issue['subject'], note['related_issues']
                    )))
                else:
                    note_text = note['note_text']

                release_notes += '* %s %s\n' % (ids, note_text)

            release_notes += '\n'
        
        return release_notes

    def complete_notes_with_gpt(self, limit):

        client = OpenAI(
            api_key = self.gpt_api_key
        )

        notes_count = 0

        for section in self.release_notes['sections']:
            
            for note in section['section_notes']:
                
                message = (self.gpt_how_to_compose_note 
                           + '\n\n' + str(note['related_issues']))

                completion = client.chat.completions.create(
                    model = self.gpt_model,
                    store = False,
                    messages = [{
                        'role': 'user',
                        'content': message
                    }]
                )

                note['note_text'] = completion.choices[0].message.content
                notes_count += 1

                # limit == 0 means no limit
                if notes_count == limit:
                    return

def save_as_json(data, file_name):
    
    with open(f'{file_name}', 'w', encoding = 'utf8') as file:
        file.write(json.dumps(data, ensure_ascii = False))

def get_from_json(file_name):

    try:
        with open(f"{file_name}", "r", encoding = "utf8") as file:
            return dict(json.loads(file.read()))
    except:
        return {}

def save_as_text(data, file_name):

    with open(f'{file_name}', 'w', encoding = 'utf8') as file:
        file.write(data)

def get_from_text(file_name):

    try:
        with open(file_name, 'r', encoding = 'utf8') as file:
            return file.read()
    except:
        return ''

def exit_if(statement, message):
    
    if statement == True:
        print(message)
        sys.exit(2)


ap = argparse.ArgumentParser(
    prog = 'Redmine release assistant',
    description = 'Helps fetch issue data for a Version \
        and create release notes with the help of ChatGPT',
)

ap.add_argument('-c', '--config', required = True,
                help = 'config filename')
ap.add_argument('-d', '--depersconfig', default = 'depersconfig.json',
                help = 'deprsonalization config filename')
ap.add_argument('-i', '--issuedata',
                help = 'provide issue data json to skip fetching')
ap.add_argument('-n', '--notessource',
                help = 'provide issue data json to skip fetching \
                    and release notes source generation')
ap.add_argument('-g', '--usegpt', action = 'store_true',
                help = 'use chatGPT to create natural language notes')
ap.add_argument('-m', '--messageforgpt',
                help = 'instructions file how to compose a note for chatGPT')
ap.add_argument('-l', '--limitforgpt', type = int,
                help = 'limit notes count to compose with chatGPT \
                    (for thrifty instructions testing)')

args = vars(ap.parse_args())

settings_file_name = args['config']
depers_settings_file_name = args['depersconfig']

issue_data_file = args['issuedata']
issue_data_provided = not (issue_data_file == None)

notes_source_file = args['notessource']
notes_source_provided = not (notes_source_file == None)

use_gpt = args['usegpt']
chatgpt_notes_limit = args['limitforgpt']

gpt_how_to_compose_note = ''

if use_gpt:

    gpt_how_to_compose_note_file = args['messageforgpt']
    gpt_how_to_compose_note = get_from_text(gpt_how_to_compose_note_file)

    exit_if(
        gpt_how_to_compose_note == '',
        'Please provide text how to compose a note for ChatGPT'
    )

settings = get_from_json(settings_file_name)
exit_if(
    settings == {},
    'Config file not found'
)

depers_settings = get_from_json(depers_settings_file_name)
settings['depers_settings'] = depers_settings
settings['gpt_how_to_compose_note'] = gpt_how_to_compose_note


assistant = RedmineReleaseAssistant(settings)

if issue_data_provided and not notes_source_provided:

    assistant.issues_data = get_from_json(issue_data_file)
    exit_if(
        assistant.issues_data == {},
        'Error reading issues data file'
    )

else:
    assistant.fetch_issues_data()
    assistant.depersonalize()

if notes_source_provided:

    assistant.release_notes = get_from_json(notes_source_file)
    exit_if(
        assistant.release_notes == {},
        'Error reading release notes source file'
    )

else:
    assistant.create_release_notes()

if use_gpt:
    assistant.complete_notes_with_gpt(chatgpt_notes_limit)

release_notes = assistant.release_notes_as_textile()

if not issue_data_provided and not notes_source_provided:

    save_as_json(
        assistant.issues_data,
        f'issue_data_{assistant.version_id}_{assistant.version_name}.json'
    )

    save_as_json(
        assistant.depers_settings,
        depers_settings_file_name)

if not notes_source_provided or use_gpt:

    save_as_json(
        assistant.release_notes,
        f'release_notes_source_{assistant.version_id}_{assistant.version_name}'
            + f'{'_gpt' if use_gpt else ''}.json')

save_as_text(
    release_notes, 
    f'release_notes_{assistant.version_name}'
        + f'{'_gpt' if use_gpt else ''}.txt'
)
