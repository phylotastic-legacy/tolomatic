#!/usr/bin/perl

use strict;
use warnings;

print "Content-type: text/plain\n\n";
print "Starting unpacking now.\n";

print "Turned off: doing nothing!";
chdir('../examples');
system('tar -jxvf tree2tabled.tar.bz2');

print "All done!";
