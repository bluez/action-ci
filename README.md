# bzcafe
BlueZ Ci Automation FramEwork


## Local CI

To run kernel CI locally for eg. PR 707, do:

    mkdir -p work
    git clone --depth 1 https://github.com/bluez/bluetooth-next work/src
    git clone --depth 1 https://github.com/bluez/bluez work/bluez

    export IMG=$(docker build -q .)
    docker run --device /dev/kvm --volume $PWD/work:/work/base:O $IMG localci kernel bluez/bluetooth-next 707
    docker run --device /dev/kvm --volume $PWD/work:/work/base:O $IMG localci user bluez/bluez 2491
