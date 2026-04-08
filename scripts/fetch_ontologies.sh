#!/usr/bin/env bash
# Downloads external ontologies into ontologies/.
# Custom ontologies (bridges/, cso/) are maintained in version control.
set -euo pipefail

ONTOLOGIES_DIR="$(cd "$(dirname "$0")/.." && pwd)/ontologies"

# ---------------------------------------------------------------------------
# Git repositories
# ---------------------------------------------------------------------------
clone_or_pull() {
    local dir="$1" url="$2" branch="${3:-}"
    local target="$ONTOLOGIES_DIR/$dir"

    if [ -d "$target/.git" ]; then
        printf '  pull  %s\n' "$dir"
        git -C "$target" pull --ff-only --quiet
    else
        printf '  clone %s\n' "$dir"
        rm -rf "$target"
        local args=(clone --depth=1)
        [ -n "$branch" ] && args+=(--branch "$branch")
        git "${args[@]}" "$url" "$target" --quiet
    fi
}

echo "==> Git repositories"
clone_or_pull CommonCoreOntologies \
    https://github.com/CommonCoreOntology/CommonCoreOntologies.git

clone_or_pull d3fend-ontology \
    https://github.com/d3fend/d3fend-ontology.git develop

clone_or_pull ontology \
    https://github.com/iofoundry/ontology

clone_or_pull fibo \
    https://github.com/edmcouncil/fibo.git master

clone_or_pull lkif-core \
    https://github.com/RinkeHoekstra/lkif-core.git

clone_or_pull ai-atlas-nexus \
    https://github.com/IBM/ai-atlas-nexus.git main

# ---------------------------------------------------------------------------
# OMG Commons (22 modules)
# https://www.omg.org/spec/Commons/
# ---------------------------------------------------------------------------
COMMONS_MODULES=(
    AnnotationVocabulary
    TextDatatype
    Collections
    StructuredCollections
    Designators
    ContextualDesignators
    Identifiers
    ContextualIdentifiers
    CodesAndCodeSets
    Classifiers
    DatesAndTimes
    Documents
    Languages
    Locations
    QuantitiesAndUnits
    RolesAndCompositions
    PartiesAndSituations
    Organizations
    BusinessAuthorizations
    RegistrationAuthorities
    RegulatoryAgencies
    SitesAndFacilities
)

echo "==> OMG Commons (${#COMMONS_MODULES[@]} modules)"
mkdir -p "$ONTOLOGIES_DIR/commons"
for mod in "${COMMONS_MODULES[@]}"; do
    dest="$ONTOLOGIES_DIR/commons/${mod}.rdf"
    if [ -f "$dest" ]; then
        printf '  skip  %s (exists)\n' "$mod"
        continue
    fi
    printf '  fetch %s\n' "$mod"
    curl -sfL \
        -H "Accept: application/rdf+xml" \
        "https://www.omg.org/spec/Commons/${mod}/" \
        -o "$dest"
done

# ---------------------------------------------------------------------------
# OBO Foundry ontologies
# ---------------------------------------------------------------------------
declare -A OBO_FILES=(
    [ogms.owl]="http://purl.obolibrary.org/obo/ogms.owl"
    [mondo-base.owl]="http://purl.obolibrary.org/obo/mondo/mondo-base.owl"
    [hp-base.owl]="http://purl.obolibrary.org/obo/hp/hp-base.owl"
    [uberon-base.owl]="http://purl.obolibrary.org/obo/uberon/uberon-base.owl"
    [maxo.owl]="http://purl.obolibrary.org/obo/maxo.owl"
    [oae.owl]="http://purl.obolibrary.org/obo/oae.owl"
    # Protected characteristics / demographics (bias testing across all domains)
    [gsso.owl]="http://purl.obolibrary.org/obo/gsso.owl"                # Gender, Sex, Sexual Orientation (~4k entities, CC BY-NC-ND 4.0)
    [hancestro.owl]="http://purl.obolibrary.org/obo/hancestro.owl"      # Human Ancestry (~1,310 classes, CC BY 4.0)
    # Social entities / insurance roles
    [omrse.owl]="http://purl.obolibrary.org/obo/omrse.owl"              # Social Entities (~100+ classes, CC BY 4.0)
    # Data use conditions / privacy governance
    [duo.owl]="http://purl.obolibrary.org/obo/duo.owl"                  # Data Use Ontology (~100 classes, CC BY 4.0)
)

echo "==> OBO Foundry (${#OBO_FILES[@]} ontologies)"
mkdir -p "$ONTOLOGIES_DIR/obo"
for file in "${!OBO_FILES[@]}"; do
    dest="$ONTOLOGIES_DIR/obo/$file"
    if [ -f "$dest" ]; then
        printf '  skip  %s (exists)\n' "$file"
        continue
    fi
    printf '  fetch %s\n' "$file"
    curl -sfL "${OBO_FILES[$file]}" -o "$dest"
done

# Fix GSSO: two triples use xml:lang="e" (invalid BCP47) instead of "en",
# which causes oxigraph's strict parser to reject the entire file.
GSSO_FILE="$ONTOLOGIES_DIR/obo/gsso.owl"
if [ -f "$GSSO_FILE" ] && grep -q 'xml:lang="e"' "$GSSO_FILE"; then
    printf '  fix   gsso.owl (invalid lang tag "e" -> "en")\n'
    sed -i '' 's/xml:lang="e"/xml:lang="en"/g' "$GSSO_FILE"
fi

# ---------------------------------------------------------------------------
# LKIF Core: generate rdfs:label for classes that lack them.
# LKIF uses URI fragments as class names (e.g. norm.owl#Prohibition) but
# has no rdfs:label annotations. The labels file makes them indexable.
# ---------------------------------------------------------------------------
LKIF_LABELS="$ONTOLOGIES_DIR/bridges/lkif-labels.ttl"
LKIF_DIR="$ONTOLOGIES_DIR/lkif-core"
if [ -d "$LKIF_DIR" ] && [ ! -f "$LKIF_LABELS" ]; then
    printf '  gen   lkif-labels.ttl (rdfs:label from URI fragments)\n'
    python3 -c "
import rdflib, glob, sys
from rdflib import OWL, RDF, RDFS, SKOS, URIRef
g = rdflib.Graph()
for f in sorted(glob.glob('$LKIF_DIR/*.owl')):
    g.parse(f)
lines = [
    '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .',
    '@prefix owl:  <http://www.w3.org/2002/07/owl#> .',
    '',
    '<https://www.commoncoreontologies.org/bridges/lkif-labels>',
    '    a owl:Ontology ;',
    '    rdfs:label \"LKIF Core Labels\" ;',
    '    rdfs:comment \"Generated rdfs:label triples for LKIF Core classes that lack labels.\" .',
    '',
]
for cls in sorted(g.subjects(RDF.type, OWL.Class)):
    if not isinstance(cls, URIRef): continue
    uri = str(cls)
    if 'estrellaproject.org/lkif-core' not in uri: continue
    if any(g.objects(cls, RDFS.label)) or any(g.objects(cls, SKOS.prefLabel)): continue
    fragment = uri.rsplit('#', 1)[-1]
    lines.append(f'<{uri}> rdfs:label \"{fragment.replace(chr(95), chr(32))}\" .')
with open('$LKIF_LABELS', 'w') as f:
    f.write('\n'.join(lines) + '\n')
print(f'  gen   {len(lines) - 8} labels written', file=sys.stderr)
" 2>/dev/null
fi

# ---------------------------------------------------------------------------
# DRON (optional — ~650 MB, excluded from indexing)
# ---------------------------------------------------------------------------
DRON_DEST="$ONTOLOGIES_DIR/dron-base.owl"
if [ -f "$DRON_DEST" ]; then
    echo "==> DRON (skip, exists — ~650 MB)"
else
    echo "==> DRON (fetching — ~650 MB, this will take a while)"
    curl -sfL http://purl.obolibrary.org/obo/dron/dron-base.owl -o "$DRON_DEST"
fi

echo "==> Done"
