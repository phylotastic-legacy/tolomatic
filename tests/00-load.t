#!perl -T

use Test::More tests => 1;

BEGIN {
    use_ok( 'Test::WWW::Mechanize' );
    use_ok( 'HTTP::Async' );
}

diag( "Testing Tolomatic, Perl $], $^X" );
