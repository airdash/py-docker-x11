# py-docker-x11

Disclaimer: THIS IS WIP, and is currently undergoing refactoring. Everything here is subject to change, may break in weird ways, 
may lack input validation, etc. There are quite a few circumstances where a newly created profile may require sudo to set up the 
profile, for example. This isn't by design, and is definitely a FIXME. py-docker-x11 should be run with a user-namespaced
Docker daemon, and this will be enforced in the future.

A repository of builds can be found [here](https://github.com/airdash/py-docker-x11-builds)

py-docker-x11 is a highly opinionated way of running (x11) apps on Docker. There's support for "profiles", i.e.
separate states for individual logical users as first class citizens, a build system that provides 
resolution for external dependencies, and proven use cases for WINE as well as (currently nvidia)
accelerated applications.

The main gist is that a yaml file embedded as a label in the image provides sane defaults for running any given image.
The build system keeps not only the application dependencies up to date, but also keeps things like embedded video drivers 
and their associated libraries up to date and in-sync with the host system. The build system also provides a DAG
if run locally, and can determine inter-dependent images and build those as well.

Example screenshots:

![Final Fantasy XIV in WINE](/screenshots/py-docker-x11-1.jpg)
![Arduino IDE for Linux](/screenshots/py-docker-x11-2.jpg)

py-docker-x11 is designed to run with a user namespaced Docker daemon, and in fact it is absolutely recommended that you
run it in this way. While the images inside of the py-docker-x11-builds repository are also designed to run as an unprivileged user, 
user-namespacing will ensure that the Docker daemon itself is also unprivileged.
