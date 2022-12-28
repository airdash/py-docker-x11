import os
import re
import subprocess
import git
from distutils.version import LooseVersion

## Driver resolution functions

def get_video_card():
    output = subprocess.check_output(["lspci", "-v"]).decode('utf-8')
    manufacturer = re.search(r".*VGA compatible.*: ([A-Za-z]+)|.*3D Controller.*", output)

    if manufacturer:
        return manufacturer.group(1).lower()
    else:
        return None

def pull_video_driver(driver_cache_path, docker_build_path):
    if get_video_card() == 'nvidia':
        from build import nvidia_driver
        result = nvidia_driver.pull(driver_cache_path, docker_build_path)
    return result

## Dependency resolution functions

def resolve_git_dependencies(dependencies):
    for dependency in dependencies:
        local_path = dependency.get("local_path")
        remote_url = dependency.get("remote_url")
        shallow = dependency.get("shallow", False)
        branch = dependency.get("branch")
        get_latest_tag_by_date = dependency.get("get_latest_tag_by_date", False)
        get_latest_tag_by_symver = dependency.get("get_latest_tag_by_symver", False)
        tag_regex = dependency.get("tag_regex", False)

        # Create the local directory if it doesn't exist
        if not os.path.exists(local_path):
            try:
                os.makedirs(local_path)
            except OSError:
                print(f"Unable to create directory {local_path}")
                return False

        if not os.path.exists(os.path.join(local_path, ".git")):
            # Clone the repository if it doesn't exist
            try:
                print(f"Cloning repository: {remote_url}")
                if shallow:
                    repo = git.Repo.clone_from(remote_url, local_path, depth=1)
                else:
                    repo = git.Repo.clone_from(remote_url, local_path)
            except git.exc.GitCommandError as e:
                print(f"Unable to clone repository: {e}")
                return False
        else:
            repo = git.Repo(local_path)
            # Pull the latest changes if the repository already exists
            try:
                print(f"Pulling existing branch: {remote_url}")
                repo.remotes.origin.fetch(tags=True)
                default_branch = repo.remotes.origin.refs.HEAD.ref.remote_head
                repo.git.checkout(default_branch)
                repo.remotes.origin.pull()
            except git.exc.GitCommandError as e:
                print(f"Unable to pull latest commit: {e}")
                return False

        # Update submodules
        for submodule in repo.submodules:
            try:
                submodule.update(init=True, recursive=True)
            except git.exc.GitCommandError as e:
                print(f"Unable to update submodule {submodule.name}: {e}")
                return False

        # Check out the specified branch if it exists
        if branch:
            try:
                repo.git.checkout(branch)
            except git.exc.GitCommandError:
                print(f"Unable to check out branch {branch}, please specify a correct branch in the dependency config.")
                return False

        elif (get_latest_tag_by_date and tag_regex) or get_latest_tag_by_symver:
            tags = repo.tags
            try:
                if get_latest_tag_by_date:
                    # Filter tags by regex
                    filtered_tags = [tag for tag in tags if re.match(tag_regex, tag.name)]
                    # Get the latest tag by commit datetime
                    latest_tag = max(filtered_tags, key=lambda x: x.commit.committed_datetime)
                elif get_latest_tag_by_symver:
                    symver_regex = r'^\d+(\.\d+)*$'
                    filtered_tags = [tag for tag in tags if re.match(symver_regex, tag.name)]
                    sorted_tags = sorted(filtered_tags, key=lambda x: LooseVersion(x.name))
                    latest_tag = sorted_tags[-1]
                repo.git.checkout(latest_tag.name)
            except ValueError:
                print("Could not determine latest tag from repository based on regex, please check your syntax.")
                return False
                # Check out the latest tag if specified

    print("Git dependency resolution complete.")
    return True

def resolve_script_dependencies(scripts, build_dir):

    # Ensure we're in the build directory so relative scripts work
    # Probably need some additional checking to ensure we're not somewhere we shouldn't be
    print("cwd is %s" % os.getcwd())
    print("build_dir is %s" % build_dir)
    if os.getcwd() != build_dir:
        os.chdir(build_dir)

    for script in scripts:
        script_path = os.path.join(os.getcwd(), "scripts", script.get("script"))
        args = script.get("args", [])

        if not os.path.exists(script_path):
            print("Script not found in scripts in app_config scripts entry. Skipping.")
            continue

        command = [script_path] + args
        print("Executing %s" % command)
        result = subprocess.Popen(command, cwd=os.getcwd(), env={})
        if result.wait() != 0:
            print("Error encountered while running %s" % command)

