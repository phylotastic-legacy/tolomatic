#!/usr/bin/perl

=head1 NAME

phylotastic_cgi.t - Tests for the phylotastic.cgi script

=head1 SYNOPSIS

    perl phylotastic_cgi.t
    SCRIPT_URL='http://localhost/script/phylotastic.cgi' perl phylotastic_cgi.t
    prove phylotastic_cgi.t

=cut

use strict;
use warnings;

use Test::More tests => 4;
use Test::WWW::Mechanize;
use HTTP::Async;

my $SCRIPT_URL = $ENV{'SCRIPT_URL'};
$SCRIPT_URL = "http://phylotastic-wg.nescent.org/script/phylotastic.cgi"
    unless defined $SCRIPT_URL;

my $mech = Test::WWW::Mechanize->new;

subtest 'Test user-facing content' => sub {
    plan tests => 5;

    $mech->get_ok($SCRIPT_URL);
    $mech->title_like(qr/phylotastic/i);

    # The first letters are missing as these tests are case-sensitive.
    $mech->text_contains('hylotastic');
    $mech->text_contains('API');
    $mech->text_contains('ource code');
};

subtest 'Try every example listed on the website' => sub {
    plan tests => 6;

    # Great apes.
    $mech->get_ok($SCRIPT_URL);
    $mech->submit_form_ok({
        form_number => 1,
        fields => {
            'species' => 'Homo sapiens, Pan troglodytes, Gorilla gorilla, Pongo pygmaeus',
            'tree' => 'mammals',
            'format' => 'newick'
        }
    }, "Submitting form for great apes/mammals/newick");
    $mech->content_is("(((Gorilla_gorilla,(Homo_sapiens,Pan_troglodytes)),Pongo_pygmaeus));\x{0a}\x{0a}", "Correct tree returned for great apes/mammals/newick");

    # pets
    $mech->get_ok($SCRIPT_URL);
    $mech->submit_form_ok({
        form_number => 1,
        fields => {
            'species' => 'Felis silvestris, Canis lupus, Cavia porcellus, Mustela nigripes',
            'tree' => 'mammals',
            'format' => 'newick'
        }
    }, "Submitting form for pets/mammals/newick");
    $mech->content_is("((Felis_silvestris,(Mustela_nigripes,Canis_lupus)),Cavia_porcellus);\x{0a}\x{0a}", 
        "Correct tree returned for pets/mammals/newick");

    # TODO: finish this.
};

subtest 'Do we get an error if we give an incorrect tree?' => sub {
    plan tests => 1;

    $mech->get_ok($SCRIPT_URL);
    $mech->submit_form_ok({
        form_number => 1,
        fields => {
            'species' => 'Homo sapiens, Pan troglodytes, Gorilla gorilla, Pongo pygmaeus',
            'tree' => 'fishes',
            'format' => 'newick'
        }
    }, "Submitting form for great apes/fishes/newick");
    $mech->text_contains("atal error");
};

subtest 'See if I can reproduce the twice-at-once error' => sub {
    plan tests => 2;

    my $uri = URI->new($SCRIPT_URL);
    $uri->query_form(
        species => 'Felis silvestris, Canis lupus, Cavia porcellus, Mustela nigripes',
        tree => 'mammals',
        format => 'newick'
    );

    my $async = HTTP::Async->new;
    $async->add(HTTP::Request->new(GET => $uri));
    $async->add(HTTP::Request->new(GET => $uri));

    while ( my $response = $async->wait_for_next_response ) {
        is($response->decoded_content, 
            "((Felis_silvestris,(Mustela_nigripes,Canis_lupus)),Cavia_porcellus);\x{0a}\x{0a}", 
            "Output as expected"
        );
    }
};
