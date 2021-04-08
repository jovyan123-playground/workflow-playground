import os
from pathlib import Path
import re
import shlex
import shutil
from subprocess import check_output, CalledProcessError, PIPE
import sys

from ghapi.core import GhApi
from github_activity import generate_activity_md
from pypandoc import convert_text


def run(cmd, **kwargs):
    """Run a command as a subprocess and get the output as a string"""
    if not kwargs.pop("quiet", False):
        print(f"+ {cmd}")
    else:
        kwargs.setdefault("stderr", PIPE)

    parts = shlex.split(cmd)
    if "/" not in parts[0]:
        executable = shutil.which(parts[0])
        if not executable:
            raise CalledProcessError(1, f'Could not find executable "{parts[0]}"')
        parts[0] = executable

    try:
        return check_output(parts, **kwargs).decode("utf-8").strip()
    except CalledProcessError as e:
        print("output:", e.output.decode("utf-8").strip())
        print("stderr:", e.stderr.decode("utf-8").strip())
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

    run('git config --global user.email "foo@example.com"')
    run('git config --global user.name "foo"')

    run(f"git clone https://github.com/{repo} test")
    prev_dir = os.getcwd()
    os.chdir("test")
    default_branch = run("git branch --show-current")

    branch = branch or default_branch

    run(f'git remote set-url origin https://github.com/{repo}')
    run(f'git fetch origin {branch} --tags')

    since = run(f"git --no-pager tag --sort=-creatordate --merged origin/{branch}")
    if not since:  # pragma: no cover
        raise ValueError(f"No tags found on branch {branch}")

    os.chdir(prev_dir)
    shutil.rmtree(Path(prev_dir) / "test")

    since = since.splitlines()[0]
    branch = branch.split("/")[-1]
    print(f"Getting changes to {repo} since {since} on branch {branch}...")

    md = generate_activity_md(
        repo, since=since, kind="pr", heading_level=2, branch=branch
    )

    if not md:
        print("No PRs found")
        return f"## New Version\n\nNo merged PRs"

    entry = md.replace("full changelog", "Full Changelog")

    entry = entry.splitlines()

    for (ind, line) in enumerate(entry):
        if re.search(r"\[@meeseeksmachine\]", line) is not None:
            match = re.search(r"Backport PR #(\d+)", line)
            if match:
                entry[ind] = format_pr_entry(target, match.groups()[0])

    entry = "\n".join(entry).strip()

    output = f"""
{entry}
""".strip()

    return output


if __name__ == '__main__':
    # https://docs.github.com/en/actions/creating-actions/metadata-syntax-for-github-actions#inputs
    target = sys.argv[-1]
    branch = os.environ.get('INPUT_BRANCH')
    convert_to_rst = os.environ.get('INPUT_CONVERT_TO_RST')
    print('Generating changelog')
    print('target:', target)
    print('branch:', branch)
    print('convert to rst:', convert_to_rst)
    output = get_version_entry(branch, target)
    if convert_to_rst == 'true':
        output = convert_text(output, 'rst', 'markdown')
    print('\n\n------------------------------')
    print(output, '------------------------------\n\n')
    Path('changelog.md').write_text(output, encoding='utf-8')
