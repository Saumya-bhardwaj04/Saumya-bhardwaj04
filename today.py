import requests
import os
from lxml import etree

# Personal access token — set as repo secret ACCESS_TOKEN
HEADERS = {'authorization': 'token ' + os.environ.get('ACCESS_TOKEN', '')}
USER_NAME = os.environ.get('USER_NAME', 'Saumya-bhardwaj04')

QUERY_COUNT = {
    'user_getter': 0,
    'follower_getter': 0,
    'graph_repos_stars': 0,
    'graph_commits': 0,
}


def simple_request(func_name, query, variables):
    request = requests.post(
        'https://api.github.com/graphql',
        json={'query': query, 'variables': variables},
        headers=HEADERS
    )
    if request.status_code == 200:
        return request
    raise Exception(func_name, 'failed with', request.status_code, request.text)


def graph_repos_stars(count_type, owner_affiliation, cursor=None):
    """
    Returns total repository count or total star count for the user.
    """
    QUERY_COUNT['graph_repos_stars'] += 1
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers {
                                totalCount
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(graph_repos_stars.__name__, query, variables)
    data = request.json()['data']['user']['repositories']

    if count_type == 'repos':
        return data['totalCount']
    elif count_type == 'stars':
        stars = sum(e['node']['stargazers']['totalCount'] for e in data['edges'])
        if data['pageInfo']['hasNextPage']:
            stars += graph_repos_stars('stars', owner_affiliation, data['pageInfo']['endCursor'])
        return stars


def graph_commits(login):
    """
    Returns total all-time commit count using contributionsCollection across all years.
    """
    QUERY_COUNT['graph_commits'] += 1
    # GitHub limits contributionsCollection to 1 year at a time.
    # We sum from account creation year to current year.
    import datetime
    current_year = datetime.datetime.utcnow().year

    # Get account creation year first
    user_query = '''
    query($login: String!){
        user(login: $login) {
            createdAt
        }
    }'''
    req = simple_request('user_created', user_query, {'login': login})
    created_at = req.json()['data']['user']['createdAt']
    start_year = int(created_at[:4])

    total = 0
    for year in range(start_year, current_year + 1):
        start = f"{year}-01-01T00:00:00Z"
        end   = f"{year}-12-31T23:59:59Z"
        query = '''
        query($start_date: DateTime!, $end_date: DateTime!, $login: String!) {
            user(login: $login) {
                contributionsCollection(from: $start_date, to: $end_date) {
                    contributionCalendar {
                        totalContributions
                    }
                }
            }
        }'''
        variables = {'start_date': start, 'end_date': end, 'login': login}
        req = simple_request('graph_commits', query, variables)
        total += int(req.json()['data']['user']['contributionsCollection']['contributionCalendar']['totalContributions'])

    return total


def follower_getter(username):
    QUERY_COUNT['follower_getter'] += 1
    query = '''
    query($login: String!){
        user(login: $login) {
            followers {
                totalCount
            }
        }
    }'''
    request = simple_request(follower_getter.__name__, query, {'login': username})
    return int(request.json()['data']['user']['followers']['totalCount'])


def justify_format(root, element_id, new_text, length=0):
    """
    Updates the text of element_id and adjusts dots in element_id_dots to keep alignment.
    Matches Andrew's approach exactly.
    """
    if isinstance(new_text, int):
        new_text = '{:,}'.format(new_text)
    new_text = str(new_text)
    find_and_replace(root, element_id, new_text)

    just_len = max(0, length - len(new_text))
    if just_len <= 2:
        dot_map = {0: '', 1: ' ', 2: '. '}
        dot_string = dot_map[just_len]
    else:
        dot_string = ' ' + ('.' * just_len) + ' '
    find_and_replace(root, f"{element_id}_dots", dot_string)


def find_and_replace(root, element_id, new_text):
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = new_text


def svg_overwrite(filename, commit_data, star_data, repo_data, follower_data):
    """
    Parse the SVG and update all stats elements by their id attributes.
    Matches Andrew's svg_overwrite pattern.
    """
    tree = etree.parse(filename)
    root = tree.getroot()

    # length args control dot-padding to keep right-side alignment
    justify_format(root, 'repo_data',     repo_data,     9)
    justify_format(root, 'star_data',     star_data,     25)
    justify_format(root, 'commit_data',   commit_data,   25)
    justify_format(root, 'follower_data', follower_data, 24)

    tree.write(filename, encoding='utf-8', xml_declaration=True)
    print(f"Updated {filename}: repos={repo_data}, stars={star_data}, commits={commit_data}, followers={follower_data}")


if __name__ == '__main__':
    print('Fetching GitHub stats for', USER_NAME, '...')

    repo_data     = graph_repos_stars('repos', ['OWNER'])
    star_data     = graph_repos_stars('stars', ['OWNER'])
    commit_data   = graph_commits(USER_NAME)
    follower_data = follower_getter(USER_NAME)

    print(f"  Repos:     {repo_data}")
    print(f"  Stars:     {star_data}")
    print(f"  Commits:   {commit_data}")
    print(f"  Followers: {follower_data}")

    svg_overwrite('assets/dark_mode.svg', commit_data, star_data, repo_data, follower_data)
    svg_overwrite('assets/github_stats.svg', commit_data, star_data, repo_data, follower_data)

    print('Done.')
    print('Total GraphQL API calls:', sum(QUERY_COUNT.values()))
