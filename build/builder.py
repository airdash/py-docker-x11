import re
import time
import os
import docker
from io import BytesIO
from .build_deps import *

class Builder:
    def __init__(self, args, base_config, build, client):
        self.args = args
        self.app_config = build.app_config
        self.base_config = build.base_config
        self.build_dir = build.build_dir
        self.client = client
        self.image = build.image
        self.tag = build.tag
        self.app_config = build.app_config
        self.raw_jinja = build.raw_jinja

        # self.update = args.update or args.auto
        self.update = args.update
        self.pull = args.full or args.pull
        # self.nocache = args.full or args.nocache or update
        self.nocache = args.full or args.nocache or args.auto

        self.always_full_update = self.app_config.get("always_full_update", False)

        # Check if the image exists locally or remotely
        self.image_exists_locally = client.images(name=self.image + ":" + self.tag)
        self.image_exists_remotely = False

    def run_build(self):

        # Check if the image exists locally or remotely
        image_exists_locally = self.client.images(name=self.image + ":" + self.tag)
        image_exists_remotely = False

        if image_exists_locally and not self.args.force:
            image_creation_time = image_exists_locally[0]["Created"]
            # Don't unnecessarily update too quickly
            if int(time.time()) - image_creation_time < 85900 and self.args.auto:
                print("Skipping image build as it's too new.")
                return 0

        # Resolve dependencies for the build
        self.__resolve_dependencies()

        if not image_exists_locally and self.app_config["build"].get("remote"):
            print("[WARN] Could not find image locally, attempting pull...")
            try:
                image_exists_remotely = client.pull(image, tag=tag)
            except:
                print("[WARN] Could not find image remotely.")

        dockerfile, inline_dockerfile = self.__get_dockerfile(image_exists_locally, image_exists_remotely)
        build_result = self.__build_image(dockerfile, inline_dockerfile)

    def __resolve_dependencies(self):
        # If the image requires a video driver, pull it in
        if self.app_config["build"].get("install_gpu_driver"):
            drivers_updated = self.__update_drivers()
    
        # If the app requires external code dependencies, resolve them
        if self.app_config["build"].get("dependencies", False):
            if self.app_config["build"]["dependencies"].get("git", False):
                git_dependencies = self.app_config["build"]["dependencies"]["git"]["repositories"]
                resolve_git_dependencies(git_dependencies)
            elif self.app_config["build"]["dependencies"].get("scripts", False):
                script_dependencies = self.app_config["build"]["dependencies"]["scripts"]
                resolve_script_dependencies(script_dependencies, self.build_dir)
            elif self.app_config["build"]["dependencies"].get("github_releases", False):
                github_release_dependencies = self.app_config["build"]["dependencies"]["github_releases"]
                resolve_github_release_dependencies(github_release_dependencies, self.build_dir)
    
    def __get_dockerfile(self, image_exists_locally, image_exists_remotely):
    
        dockerfile = self.app_config["build"].get("dockerfile")
        inline_dockerfile = None

        if self.update and (image_exists_locally or image_exists_remotely) and not self.always_full_update and not self.app_config["build"].get("install_gpu_driver"):
            if self.app_config["build"].get("dockerfile_update_file"):
                dockerfile = self.app_config["build"]["dockerfile_update_file"]
            elif self.app_config["build"].get("dockerfile_update") and isinstance(self.app_config["build"].get("dockerfile_update"), list):
                from_found = False
                dockerfile_update = self.app_config["build"]["dockerfile_update"]
                for line in range(len(dockerfile_update)):
                    if not re.match("FROM|RUN|COPY|ADD|ENV|USER", dockerfile_update[line]):
                        dockerfile_update[line] = "RUN " + dockerfile_update[line]
                    elif re.match("FROM", dockerfile_update[line]):
                        from_found = True
                if not from_found:
                    dockerfile_update = [f"FROM {image}:{tag}\n"] + dockerfile_update
                inline_dockerfile = BytesIO(bytes("\n".join(dockerfile_update), "utf-8"))
            elif os.path.exists("Dockerfile-update"):
                dockerfile = "Dockerfile-update"
    
        return dockerfile, inline_dockerfile
    
    def __build_image(self, dockerfile, inline_dockerfile):
        # Build the image
        try:
            if inline_dockerfile:
                result = self.client.build(path=self.build_dir, labels={"pdx-app-config": self.raw_jinja},
                        fileobj=inline_dockerfile, tag=self.image + ":" + self.tag, pull=self.pull, 
                        nocache=self.nocache, decode=True)
            else:
                result = self.client.build(path=self.build_dir, labels={"pdx-app-config": self.raw_jinja},
                        dockerfile=dockerfile, tag=self.image + ":" + self.tag, pull=self.pull, 
                        nocache=self.nocache, decode=True)
    
            for log in result:
                print(log.get('stream'))

            return True

        except docker.errors.BuildError as e:
            print("[ERROR] Docker build failed:")
            print(e)
            exit(1)
        except docker.errors.APIError as e:
            print("[ERROR] Docker API error:")
            print(e)
            exit(1)

    
    def __update_drivers(self):
    
        driver_cache_path = os.path.expanduser(self.base_config["appDirs"].get("driver_cache"))
        docker_build_path = self.build_dir
        result = pull_video_driver(driver_cache_path, docker_build_path)
        return result
    
    def __push_image(self):
        # Save the build configs to variables
        base_build_config = base_config.get("build")
        app_build_config = app_config.get("build")
    
        # Check if the image should be pushed
        if push == True or base_build_config.get("always_push") == True or app_build_config.get("always_push") == True:
            print("Pushing image to %s:%s" % (app_build_config["image"], app_build_config["tag"]) )
    
            # Push the image and raise any exceptions that occur
            result = client.push(repository=app_build_config["image"], tag=app_build_config["tag"], decode=True, raise_for_status=True)
    
            print("Build successfully pushed.")
            return True
    
        return False

def main():
    pass

if __name__ == '__main__':
    main()
