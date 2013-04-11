#!/usr/bin/perl 

use strict;
use warnings;

print "Content-type: text/plain\n\nThe time is now: " . gmtime(time);

exit 0;
