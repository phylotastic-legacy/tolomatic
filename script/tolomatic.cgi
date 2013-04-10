#!/opt/perl5/perls/perl-5.16.2/bin/perl
#!/usr/bin/perl

=head1 NAME

Tolomatic - Phylotastic pruner of megatrees

=head1 SYNOPSIS

 perl tolomatic.cgi 

=head1 DESCRIPTION

This script prunes very large phylogenies down to the topology for a set of user-
defined species.

=head1 OPTIONS

=over

=item species

Species names are provided as a comma-separate list. The names need to match exactly the 
names in the megatrees. Watch out with shell names and URL-encoding!

=item tree

The following trees are available: C<fishes> - the first tree from 
Westneat_Lundberg_BigFishTree.nex, C<mammals> - the first tree from 
Bininda-emonds_2007_mammals.nex, C<tol> - the tree from TOL.xml, C<angio> - the tree from 
Smith_2011_angiosperms.txt, C<phylomatic> - the tree from Phylomatictree.nex

=item format

The following return formats are available: C<NeXML>, C<Newick>, C<Nexus>.

=item help

Prints this help message and quits.

=item verbose

Sets verbosity level, between 0 and 4.

=back

=cut

use v5.010;

use strict;
use warnings;

use Mojolicious::Lite;

use lib '../lib';
use Pod::HTML;
use Pod::Usage;
use Getopt::Long;
use Bio::Phylo::Factory;
use Bio::Phylo::IO 'unparse';
use Bio::Phylo::Util::Logger ':levels';
use File::Temp qw(tempfile tempdir);
use File::Path qw(remove_tree);
use CGI;
use Cwd;

# so this is obviously dumb, to hardcode it here. sorry. need a config system
my %source = (
	'mammals'    => 'http://localhost/examples/rawdata/Bininda-emonds_2007_mammals.nex',
	'fishes'     => 'http://localhost/examples/rawdata/Westneat_Lundberg_BigFishTree.nex',
	'tolweb'     => 'http://localhost/examples/rawdata/TOL.xml',
	'angio'      => 'http://localhost/examples/rawdata/Smith_2011_angiosperms.txt',
	'phylomatic' => 'http://localhost/examples/rawdata/Phylomatictree.nex',
	'goloboff'   => 'http://localhost/examples/rawdata/Goloboff_molecules_only_shortest.nwk.txt',
	'greengenes' => 'http://localhost/examples/rawdata/Greengenes2011.txt'
);

# current working directory
my $CWD = getcwd;

# Either GET or POST will work. 
any [qw(GET POST)] => '/' => sub {
    my $self = shift;

    # controller
    if($self->param('species')) {
        process_submission($self);
    } else {
        $self->render("frontpage");
    }
};

app->start;
exit(0);

sub process_submission {
    my $c = shift;

    my %params = (
        'species' =>    $c->param('species'),
        'trees' =>      $c->param('trees'),
        'format' =>     $c->param('format')
    );

    # make species list 
    my @species = split /,/, $params{'species'};

    # sanitize list by fixing spaces, underscores, and capitalization
    s/^\s+|\s+$//g for @species; # remove leading and trailing spaces 
    s/ /_/g for @species;  # convert internal spaces to underscores
    #
    # had to cut this out to allow use of phylomatic tree which is all lowercase names
    # tr/A-Z/a-z/ for @species; # lower-case the whole thing
    # s/^(\w)/\u$1/ for @species; # capitalize first word

    my ( $fh, $filename ) = tempfile();
    print $fh join "\n", @species;
    close $fh;

    # extend PERL5LIB for child processes
    my $PERL5LIB = join ':', @INC;

    # create temp dir
    my $TEMPDIR = tempdir(CLEANUP => 1);

    # Hadoop needs its own directory.
    $TEMPDIR .= "/results";

    # create path to DATADIR
    my $DATADIR = $CWD . '/../examples/' . lc($params{'tree'});

    # invoke hadoop
    my $error;

    $ENV{'HADOOP_HOME'} = "/usr/local/opt/hadoop";
    $ENV{'HADOOP_JAR'} = "/usr/local/opt/hadoop/libexec/contrib/streaming/hadoop-streaming-1.1.2.jar";

    my $returned = system(
        "$ENV{HADOOP_HOME}/bin/hadoop",
        'jar'       => $ENV{'HADOOP_JAR'},
            # "$ENV{HADOOP_HOME}/hadoop-$ENV{HADOOP_VERSION}-streaming.jar",
        '-cmdenv'   => 'DATADIR=' . $DATADIR,
        '-cmdenv'   => 'PERL5LIB=' . $PERL5LIB,
        '-input'    => $filename,
        '-output'   => $TEMPDIR,
        '-mapper'   => $CWD . '/pruner/mapper.pl',
        '-combiner' => $CWD . '/pruner/combiner.pl',
        '-reducer'  => $CWD . '/pruner/reducer.pl',
    );
    unless($returned == 0) {
        $c->stash('error' => "Could not run tolomatic.cgi");
        $c->render('error');
        return;
    }

    # create provenance info
    my %provenance = (
        'species' => $params{'species'},
        'treeid'  => $params{'tree'},
        'tnrs'    => 'exactMatch',
        'pruner'  => 'MapReduce',
        'source'  => $source{lc $params{'tree'}},
    );
    my $defines = join ' ', map { "--define $_='$provenance{$_}'" } keys %provenance;

    # print header
    # my $mime_type = ( $params{format} =~ /xml$/i ) ? 'application/xml' : 'text/plain';

    # print content
    my $outfile = "$TEMPDIR/part-00000";
    my $output = `$CWD/newickify.pl -i $outfile -f $params{'format'} $defines`;
    $c->render_data("$output\n", format => $params{'format'});

    # Remove the TEMPDIR.
    remove_tree($TEMPDIR);
}

__DATA__

@@ frontpage.html.ep

<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"
   "http://www.w3.org/TR/html4/loose.dtd">

<html lang="en">
<head>
	<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
	<title>Phylotastic topology server prototype using MapReduce</title>
	    <link rel="stylesheet" type="text/css" href="http://phylotastic.org/css/phylotastic.css">
</head>
    <body>
    <div class="pruner">
    <table>
    <tr> <!-- the first row with "about" and logo --> 
		<td width="25%" align="center">
			Welcome! <br>Given a list of taxa, this prototype pruner returns a phylogeny for those taxa based on a library of source trees. 
		</td>
		<td align="center"><a href="http://www.phylotastic.org"><img src="http://www.evoio.org/wg/evoio/images/f/f1/Phylotastic_logo.png"/></a>
		<br>Automated access to the Tree of Life
		</td>
		<td><!-- intentionally blank, could be used for sponsor logos -->
		</td>
    </tr>
    <tr bgcolor="#61D27F"> <!-- second row with form on right, instructions on left -->
		<td align="center"> <!-- how to do the demo --> 
			<b>Try it!</b>
			<br>
			Using the form at right, enter a list of scientific names, select a source tree, and click "Get Phylotastic Tree!"
		</td>
		<form action="tolomatic.cgi" method="post"> <!-- the form --> 
		<fieldset>
		<td align="left">			
				<br>
				<label for="speciesList">Species list:</label>
				<textarea cols="70" rows="3" id="speciesList" name="species" class="species">Homo sapiens, Pan troglodytes, Gorilla gorilla, Pongo pygmaeus</textarea>		
			   <label for="treeSelector">Source tree:</label>
				<select name="tree" id="treeSelector">
					<option value="mammals">mammals</option>				
					<option value="fishes">fishes</option>
					<option value="tolweb">tolweb</option>
					<option value="angiosperms">angiosperms</option>
					<option value="phylomatic">phylomatic</option>
					<option value="goloboff">goloboff</option>
					<option value="greengenes">greengenes</option>
				</select>
				<label for="formatSelector">Output format:</label>
				<select name="format" id="formatSelector">
					<option value="newick">Newick</option>
					<option value="nexus">Nexus</option>
					<option value="nexml">NeXML</option>
					<option value="nexml">PhyloXML</option>					
				</select>
		</td>
		<td>
			 <input value="Get Phylotastic Tree!" type="submit"/>
		</td>
		</fieldset>
		</form>
	</tr>
    <tr  bgcolor="#E6E6E6"> <!-- third row with examples on right, instructions on left -->
	<td align="center">Or, you can just copy and paste one of the examples here
	</td>
	    <td colspan="2"> 
		<table class="examples" border="1"> <!-- the table of examples -->
			<tr>
				<th>Example</th><th>Source tree</th><th>Species list (copy and paste)</th>
			</tr>
			<tr>
				<td>great apes</td><td>mammals</td><td>Homo sapiens, Pan troglodytes, Gorilla gorilla, Pongo pygmaeus</td>
			</tr>
			<tr>
				<td>pets</td><td>mammals</td><td>Felis silvestris, Canis lupus, Cavia porcellus, Mustela nigripes</td>
			</tr>
			<tr>
				<td>musical fish families</td><td>fishes</td><td>Aulostomidae, Rhinobatidae, Syngnathidae, Sciaenidae</td>
			</tr>
			<tr>
				<td>tree nuts</td><td>angio</td><td>Macadamia integrifolia, Pinus edulis, Corylus heterophylla, Pistacia vera, Castanea dentata, Juglans nigra, Prunus dulcis, Bertholletia excelsa</td>
			</tr>
			<tr>
				<td>cool ants</td><td>tolweb</td><td>Oecophylla smaragdina,  Camponotus inflatus, Myrmecia pilosula</td>
			</tr>
			<tr>
				<td>tree nuts (genera)</td><td>phylomatic</td><td>macadamia integrifolia, pinus, corylus heterophylla, pistacia, castanea, juglans, prunus, bertholletia</td>
			</tr>
		</table>    
    </td>
	</tr>
    </table>
		<ul class="information" align="left">
		<li><b>What's missing?</b>This prototype uses exact matching with names in source trees (so be sure to get the exact scientific name, and follow the capitalization rules in the examples), but a more robust system would correct typos, fix capitalization, and use a Taxonomic Name Resolution Service (TNRS) that recognizes synonyms (and perhaps, common names).  A more flexible system might allow taxonomic grafting (i.e., adding a species based on its genera or family).  This service returns only a topology, without branch lengths or other information, whereas a more complete phylotastic system would supply branch lengths and provenance information.  
		<li><b>How it works</b>.  Pruning can be done by recursive calls into a database (which probably would need to hit the database many times) or by loading the whole tree into memory (which might take a while to read in the file, and cost a bit of memory).  The way it is done here is much cooler, because it never requires the whole tree to be in memory or in a database: the pruning is done in parallel using <a href="http://en.wikipedia.org/wiki/MapReduce">MapReduce</a>.  Some tests on the entire dump of the <a href="http://tolweb.org">Tree of Life Web Project</a> showed that this returns a pruned subtree within a few seconds, fast enough for a web service.  To find out more, read the <a href="https://github.com/phylotastic/tolomatic/blob/master/README.pod">online docs at github</a>. 
		<li><b>Source trees</b>.  Some information on the source trees used in this project is as follows: 
		<ul class="littleul">
		<li><b>mammals</b>: 4500 mammal species from Bininda-Emonds, et al. 2007. 
		<li><b>fishes</b>: fish families from Westneat & Lundberg
		<li><b>tolweb</b>: XML dump of entire phylogeny from tolweb.org
		<li><b>angio</b>: Smith, et al., 2011 phylogeny of angiosperms
		<li><b>phylomatic</b>: plant framework from Phylomatic (Webb & Donoghue, 2005)
		</ul>
The mammals tree includes the vast majority of known extant mammals, but the other trees are missing many known species.  Some of these trees do not include species, but only higher taxonomic units (genera, families, orders). 
		<li><b>The web-services API</b>.  This web page is just a front end to a web service!  You can call the service directly (no web page) like this:
		<br> <code>phylotastic.cgi?format=newick&tree=mammals&species=Homo_sapiens,Pan_troglodytes,Gorilla_gorilla</code>
		<li><b>Source code</b>. Source code for <a href="https://github.com/phylotastic/tolomatic/">this project</a> (and <a href="https://github.com/phylotastic/">other phylotastic projects</a>) is available at github.  
		<li><b>Musical fish?</b>  That's a joke referring to the families of Guitarfish, Trumpetfish, Pipefish, and Drum.  The tree nuts are chestnut (Castanea), almond (Prunus), hazelnut (Corylus), walnut (Juglans), Brazilnut (Bertholletia), macadamia, pine nut, and pistachio.  The pets are cat, dog, guinea pig, and ferret.  
	</div> 
    </body>
</html>

@@ error.html.ep
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"
    "http://www.w3.org/TR/html4/loose.dtd">

    <html lang="en">
    <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <title>Phylotastic topology server prototype using MapReduce</title>
    <link rel="stylesheet" type="text/css" href="http://phylotastic.org/css/phylotastic.css">
    </head>
    <body>
    <div class="pruner"><h1>An error has occured</h1>
    <div class="error"><%= $error %></div>
    <div class=pruner"><a href="tolomatic.cgi">Back to the form</a></div>
    </body>
    </html>

