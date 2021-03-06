#!/usr/bin/perl

=head1 NAME

PhyloTastic - pruner of megatrees

=head1 SYNOPSIS

 ./phylotastic.cgi --species='Homo_sapiens,Pan_troglodytes,Gorilla_gorilla' --tree=mammals --format=newick

Or, as a CGI script:
 http://example.org/cgi-bin/phylotastic.cgi?species=Homo_sapiens,Pan_troglodytes,Gorilla_gorilla&tree=mammals&format=newick

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

use lib '../lib';
use strict;
use warnings;
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

# Warning: turning the DEBUG flag on will leak LOTS
# of information to users -- please don't leave this
# on!
my $DEBUG = 1;

# Set STDOUT to unbuffered.
$| = 1;

# Figure out if we're running as a CGI script or not.
my $running_as_cgi = 0;
$running_as_cgi = 1 if exists $ENV{'QUERY_STRING'};

# If we are running as CGI, trap die() so that we display a CGI-ish error message.
my $DEBUG_DETAILS = "No debugging messages emitted.";
$DEBUG_DETAILS = "Debug flag turned off."
    unless $DEBUG;

if($running_as_cgi) {
    $SIG{__DIE__} = sub {
        my $error = $_[0];

        # If debugging is turned off, suppress the $DEBUG_DETAILS.
        $DEBUG_DETAILS = ""
            unless($DEBUG);

        print <<ERROR_PAGE;
Content-type: text/html; charset=UTF-8

<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"
    "http://www.w3.org/TR/html4/loose.dtd">

    <html lang="en">
    <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <title>Phylotastic topology server prototype using MapReduce</title>
    <link rel="stylesheet" type="text/css" href="http://phylotastic.org/css/phylotastic.css">
    </head>
    <body>
    <div class="pruner"><h1>Error</h1>
    <div class="error">$error</div>
    <div class="error" style="font-size:80%">(<a href="phylotastic.cgi">back to the form</a> or <a href="https://github.com/phylotastic/tolomatic/issues?state=open">report this error to us</a>)</div>
    </body>
    </html>

<!--
    If the debug flag is turned on, you should see debugging messages after
    this line:

    $DEBUG_DETAILS
-->

ERROR_PAGE

        exit(0);
    };
}

# so this is obviously dumb, to hardcode it here. sorry. need a config system
# (note that, currently, this source hash is used only for provenance info, not data) 
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

# process program arguments
my $cgi = CGI->new;
my %params = $cgi->Vars(",");
GetOptions(
	'help|?'    => \$params{'help'},
	'tree=s'    => \$params{'tree'},
	'species=s' => \$params{'species'},
	'format=s'  => \$params{'format'},
	'verbose+'  => \$params{'verbose'},
);

# print help message and quit
if ( $params{'help'} ) {
	if ( $cgi->param('help') ) {
		print $cgi->header;
		pod2html("pod2html","--infile=$0");
	}
	else {
		pod2usage();
	}
	exit 0;
}

# print web form and quit
if ( $running_as_cgi and not $ENV{'QUERY_STRING'} ) {
	print $cgi->header;
	print do { local $/; <DATA> };
	exit 0;
}

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
my $TEMPDIR = tempdir(DIR => $CWD . '/tmp', CLEANUP => 1);
$TEMPDIR .= "/hadoop"; # Hadoop needs an empty directory.

# create path to DATADIR
my $tree_to_search = lc($params{'tree'});
my $DATADIR = $CWD . "/../examples/$tree_to_search";

# Sanitize tree_to_search.
$tree_to_search =~ s/[^A-Za-z0-9]/_/g;

die "No tree named '$tree_to_search' has been installed on this system"
    unless(-d $DATADIR);

# invoke hadoop
my $error;
my @cmdline = (
	"$ENV{HADOOP_HOME}/bin/hadoop",
	'jar'       => "$ENV{HADOOP_HOME}/hadoop-$ENV{HADOOP_VERSION}-streaming.jar",
	'-cmdenv'   => 'DATADIR=' . $DATADIR,
	'-cmdenv'   => 'PERL5LIB=' . $PERL5LIB,
	'-input'    => $filename,
	'-output'   => $TEMPDIR,
	'-mapper'   => $CWD . '/pruner/mapper.pl',
	'-combiner' => $CWD . '/pruner/combiner.pl',
	'-reducer'  => $CWD . '/pruner/reducer.pl',
);
my $cmdline = join(' ', @cmdline) . " 2>&1";
my $output = `$cmdline`;

if($? != 0) {
    $output =~ tr/[\r\n]/\n/;

    $DEBUG_DETAILS = "Executed <<$cmdline>>\nOutput: <<$output>>.";

    if($output =~ /Need DATADIR environment variable/) {
        # Detect cases where no pre-processed tree could be found.
        die("No tree named '$tree_to_search' has been set up on this system.");
    } else {
        die("An unknown error occured in executing the Hadoop job, returned $?");
    }
    
    exit 0;
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

# determine final tree
my $outfile = "$TEMPDIR/part-00000";
my $final_tree = `$CWD/newickify.pl -i $outfile -f $params{'format'} $defines 2>&1`;

# If the final tree is blank, produce an error message.
if($final_tree =~ /Can't call method "to_newick" on an undefined value/ or $final_tree =~ /^\s*$/) {
    $DEBUG_DETAILS = "Hadoop output: <<$output>>\n\nnewickify.pl output: <<$final_tree>>"; 
    die("The taxa you searched for could not be found on tree '$tree_to_search'.");
}

# Any other errors from newickify.pl.
$DEBUG_DETAILS = $final_tree;
die("newickify.pl failed with an error, returned $?") 
    if($? != 0);

# print header
my $mime_type = ( $params{format} =~ /xml$/i ) ? 'application/xml' : 'text/plain';
print $cgi->header( $mime_type ) if $ENV{'QUERY_STRING'};

print "$final_tree\n";

# print "\n\n=====\n$output\n=====\n";

# Remove the TEMPDIR.
remove_tree($TEMPDIR);

exit 0;

__DATA__
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
		<form action="phylotastic.cgi" method="get"> <!-- the form --> 
		<fieldset>
		<td align="left">			
				<br>
				<label for="speciesList">Species list:</label>
				<textarea cols="70" rows="3" id="speciesList" name="species" class="species">Homo sapiens, Pan troglodytes, Gorilla gorilla, Pongo pygmaeus</textarea>
				<br>		
			   <label for="treeSelector">Source tree:</label>
				<select name="tree" id="treeSelector">
					<option value="mammals">mammals</option>				
					<option value="fishes">fishes</option>
					<option value="tolweb">tolweb</option>
					<option value="angiosperms">angiosperms</option>
					<option value="phylomatic">phylomatic</option>
<!-- commented out greengenes & Goloboff trees (not pre-processed, takes too long) 
					<option value="goloboff">goloboff</option>
					<option value="greengenes">greengenes</option>
-->
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
				<td>tree nuts</td><td>angio</td><td>Macadamia integrifolia, Pinus koraiensis, Corylus heterophylla, Pistacia vera, Castanea dentata, Juglans nigra, Gingko biloba, Celtis occidentalis, Prunus dulcis, Bertholletia excelsa</td>
			</tr>
			<tr>
				<td>cool ants</td><td>tolweb</td><td>Oecophylla smaragdina,  Harpegnathos saltator, Atta columbica, Cheliomyrmex morosus</td>
			</tr>
			<tr>
				<td>a few tree nuts</td><td>phylomatic</td><td>macadamia integrifolia, macadamia grandis, corylus heterophylla, corylus chinensis, prunus</td>
			</tr>
		</table>    
    </td>
	</tr>
    </table>
		<ul class="information" align="left">
                <li><b>That's not right ...</b> If you find a bug in this web service, please <a href="https://github.com/phylotastic/tolomatic/issues">write up a bug report</a> with information on the query you submitted, what response you expected, and what response you received. Thank you so much for your feedback!
                </li>
		<li><b>What's missing?</b>This prototype uses exact matching with names in source trees (so be sure to get the exact scientific name, and follow the capitalization rules in the examples), but a more robust system would correct typos, fix capitalization, and use a Taxonomic Name Resolution Service (TNRS) that recognizes synonyms (and perhaps, common names).  A more flexible system might allow taxonomic grafting (i.e., adding a species based on its genera or family).  This service returns only a topology, without branch lengths or other information, whereas a more complete phylotastic system would supply branch lengths and provenance information.  
		<li><b>How it works</b>.  Pruning can be done by recursive calls into a database (which probably would need to hit the database many times) or by loading the whole tree into memory (which might take a while to read in the file, and cost a bit of memory).  The way it is done here is much cooler, because it never requires the whole tree to be in memory or in a database: the pruning is done in parallel using <a href="http://en.wikipedia.org/wiki/MapReduce">MapReduce</a>.  Some tests on the entire dump of the <a href="http://tolweb.org">Tree of Life Web Project</a> showed that this returns a pruned subtree within a few seconds, fast enough for a web service.  To find out more, read the <a href="https://github.com/phylotastic/tolomatic/blob/master/README.pod">online docs at github</a>. 
		<li><b>Source trees</b>.  Some information on the source trees used in this project is as follows: 
		<ul class="littleul">
		<li><b><a href="http://phylotastic.org/data/Bininda-emonds_2007_mammals.nex">mammals</a></b>: 4500 mammal species from <a href="http://www.ncbi.nlm.nih.gov/pubmed/17392779">Bininda-Emonds, et al. 2007</a>.
		<li><b><a href="http://phylotastic.org/data/Westneat_Lundberg_BigFishTree.nex">fishes</a></b>: fish families from Westneat & Lundberg, unpublished.
		<li><b><a href="http://www.evoio.org/wiki/File:TOL.xml.zip">tolweb</a></b>: XML dump of entire phylogeny from tolweb.org.
		<li><b><a href="http://www.evoio.org/wiki/File:Smith_2011_angiosperms.txt">angio</a></b>: <a href="http://www.amjbot.org/content/98/3/404.full">Smith, et al., 2011</a> phylogeny of angiosperms.
<!--
		<li><b>goloboff</b>: Goloboff, et al., tree of ~ all eukaryotes in GenBank
-->
		<li><b><a href="http://www.evoio.org/wiki/File:Phylomatictree.nex">phylomatic</a></b>: plant framework from Phylomatic (Webb & Donoghue, 2005).
		</ul>
The mammals tree includes the vast majority of known extant mammals, but the other trees are missing many known species.  Some of these trees do not include species, but only higher taxonomic units (genera, families, orders). 
		<li><b>The web-services API</b>.  This web page is just a front end to a web service!  You can call the service directly (no web page) like this:
		<br> <code>phylotastic.cgi?format=newick&tree=mammals&species=Homo_sapiens,Pan_troglodytes,Gorilla_gorilla</code>
		<li><b>Source code</b>. Source code for <a href="https://github.com/phylotastic/tolomatic/">this project</a> (and <a href="https://github.com/phylotastic/">other phylotastic projects</a>) is available at github.  
		<li><b>Musical fish?</b>  That's a joke referring to the families of Guitarfish, Trumpetfish, Pipefish, and Drum.  The tree nuts are chestnut (Castanea), almond (Prunus), hazelnut (Corylus), walnut (Juglans), Brazilnut (Bertholletia), macadamia, pine nut, and pistachio.  The pets are cat, dog, guinea pig, and ferret.  
	</div> 
    </body>
</html>
