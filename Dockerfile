FROM blueztestbot/bluez-build:latest

COPY *.sh           /
COPY *.py           /
COPY config.json    /
COPY gitlint        /
COPY libs/*.py      /libs/
COPY ci/*.py        /ci/
COPY scripts/*.sh   /scripts/

ENTRYPOINT [ "/entrypoint.sh" ]
