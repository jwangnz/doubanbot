#!/bin/sh
#
# Shell script for running the jabber bot.  I'd rather use something like
# launchd, but that's unavailable to me on my servers.

while :
do
        twistd -l dbb.log -ny dbb.tac --pidfile=dbb.pid
        sleep 3
done
