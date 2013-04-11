#!/usr/bin/perl

use strict;
use warnings;

print "Content-type: text/plain\n\n";
print "Starting unpacking now.\n";

chdir('../examples');
system('tar -jxvf tree2tabled.tar.bz2');

print "All done!";
