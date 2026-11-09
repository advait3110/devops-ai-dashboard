# Jenkins controller with the Docker CLI + Compose plugin.
# The pipeline builds/tests everything inside Docker images, so Jenkins itself
# needs no Python or Node.js - it stays small.
FROM docker:28-cli AS dockercli

FROM jenkins/jenkins:lts-jdk21
USER root
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins /usr/local/libexec/docker/cli-plugins
USER jenkins
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
