import os
import re
import shlex
import shutil
from subprocess import check_output, CalledProcessError
import sys

from ghapi.core import GhApi
from github_activity import generate_activity_md
from pypandoc import convert_text


def run(cmd, **kwargs):
    """Run a command as a subprocess and get the output as a string"""
    if not kwargs.pop("quiet", False):
        print(f"+ {cmd}")

    kwargs.setdefault("stderr", PIPE)

    parts = shlex.split(cmd)
    if "/" not in parts[0]:
        executable = shutil.which(parts[0])
        if not executable:
            raise CalledProcessError(1, f'Could not find executable "{parts[0]}"')
        parts[0] = normalize_path(executable)

    try:
        return check_output(parts, **kwargs).decode("utf-8").strip()
    except CalledProcessError as e:
        print(e.output.decode("utf-8").strip())
        raise e


def format_pr_entry(target, number):
    """Format a PR entry in the style used by our changelogs.

    Parameters
    ----------
    target : str
        The GitHub owner/repo
    number : int
        The PR number to resolve

    Returns
    -------
    str
        A formatted PR entry
    """
    owner, repo = target.split("/")
    auth = os.environ['GITHUB_ACCESS_TOKEN']
    gh = GhApi(owner=owner, repo=repo, token=auth)
    pull = gh.pulls.get(number)
    title = pull.title
    url = pull.url
    user_name = pull.user.login
    user_url = pull.user.html_url
    return f"- {title} [{number}]({url}) [@{user_name}]({user_url})"


def get_version_entry(branch, repo):
    """Get a changelog for the changes since the last tag on the given branch.

    Parameters
    ----------
    branch : str
        The target branch
    repo : str
        The GitHub owner/repo

    Returns
    -------
    str
        A formatted changelog entry with markers
    """
    auth = os.environ['GITHUB_ACCESS_TOKEN']
    run(f"git clone https://github.com/{repo} test")
    cmd = "git branch --show-current"
    test = os.path.join(os.getcwd(), 'test')
    default_branch = run(cmd, cwd=test)

    branch = branch or default_branch

    run(f'git fetch origin {branch} --tags')

    since = run(f"git --no-pager tag --merged origin/{branch}", cwd=test)
    if not since:  # pragma: no cover
        raise ValueError(f"No tags found on branch {branch}")

    shutil.rmtree(test)

    since = since.splitlines()[-1]
    branch = branch.split("/")[-1]
    print(f"Getting changes to {repo} since {since} on branch {branch}...")

    md = generate_activity_md(
        repo, since=since, kind="pr", heading_level=2, branch=branch
    )

    if not md:
        print("No PRs found")
        return f"## {version}\n\nNo merged PRs"

    md = md.splitlines()

    start = -1
    full_changelog = ""
    for (ind, line) in enumerate(md):
        if "[full changelog]" in line:
            full_changelog = line.replace("full changelog", "Full Changelog")
        elif line.strip().startswith("### Merged PRs"):
            start = ind

    entry = md[start:]

    for (ind, line) in enumerate(entry):
        if re.search(r"\[@meeseeksmachine\]", line) is not None:
            match = re.search(r"Backport PR #(\d+)", line)
            if match:
                entry[ind] = format_pr_entry(match.groups()[0])

    entry = "\n".join(entry).strip()

    output = f"""
------------------------------

{full_changelog}

{entry}

------------------------------
""".strip()

    return output


if __name__ == '__main__':
    # https://docs.github.com/en/actions/creating-actions/metadata-syntax-for-github-actions#inputs
    target = sys.argv[-1]
    branch = os.environ.get('INPUT_BRANCH')
    convert_to_rst = os.environ.get('INPUT_CONVERT_TO_RST')
    output = get_version_entry(branch, target)
    if convert_to_rst == 'true':
        output = convert_text(output, 'rst', 'markdown')
    print('\n\n')
    print(output, '\n\n')
