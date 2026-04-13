"""Tests for OWL2Vec* projection, random walks, and embedding."""

import pytest
from rdflib import Graph

from ontoquery.backend import RdflibBackend
from ontoquery.owl2vec import (
    SUBCLASS_OF,
    SUPERCLASS_OF,
    ProjectedGraph,
    build_adjacency,
    project_ontology,
    random_walks,
)


EX = "http://example.org/ont#"


def _backend(ttl: str) -> RdflibBackend:
    g = Graph()
    g.parse(data=ttl, format="turtle")
    return RdflibBackend(g)


# --- Ontology fixtures ---

TAXONOMY_TTL = f"""\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <{EX}> .

ex:Animal a owl:Class ; rdfs:label "Animal" .
ex:Mammal a owl:Class ; rdfs:label "Mammal" ; rdfs:subClassOf ex:Animal .
ex:Dog a owl:Class ; rdfs:label "Dog" ; rdfs:subClassOf ex:Mammal .
ex:Cat a owl:Class ; rdfs:label "Cat" ; rdfs:subClassOf ex:Mammal .
"""

RESTRICTION_TTL = f"""\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <{EX}> .

ex:Animal a owl:Class ; rdfs:label "Animal" .
ex:Habitat a owl:Class ; rdfs:label "Habitat" .
ex:livesIn a owl:ObjectProperty .

ex:Fish a owl:Class ;
    rdfs:label "Fish" ;
    rdfs:subClassOf ex:Animal ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty ex:livesIn ;
        owl:someValuesFrom ex:Habitat
    ] .
"""

DOMAIN_RANGE_TTL = f"""\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <{EX}> .

ex:Person a owl:Class ; rdfs:label "Person" .
ex:Company a owl:Class ; rdfs:label "Company" .
ex:worksFor a owl:ObjectProperty ;
    rdfs:domain ex:Person ;
    rdfs:range ex:Company .
"""

EQUIVALENCE_TTL = f"""\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <{EX}> .

ex:Human a owl:Class ; rdfs:label "Human" .
ex:Person a owl:Class ; rdfs:label "Person" .
ex:Human owl:equivalentClass ex:Person .
"""

COMPLEX_EQUIV_TTL = f"""\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <{EX}> .

ex:Animal a owl:Class ; rdfs:label "Animal" .
ex:Habitat a owl:Class ; rdfs:label "Habitat" .
ex:livesIn a owl:ObjectProperty .

ex:WildAnimal a owl:Class ;
    rdfs:label "Wild Animal" ;
    owl:equivalentClass [
        owl:intersectionOf ( ex:Animal [
            a owl:Restriction ;
            owl:onProperty ex:livesIn ;
            owl:someValuesFrom ex:Habitat
        ] )
    ] .
"""

ANNOTATION_TTL = f"""\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex: <{EX}> .

ex:Agent a owl:Class ;
    rdfs:label "Agent" ;
    skos:definition "An entity that acts on its environment." .
"""

COMBINED_TTL = f"""\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex: <{EX}> .

ex:Agent a owl:Class ;
    rdfs:label "Agent" ;
    skos:definition "An entity that acts." .

ex:Person a owl:Class ;
    rdfs:label "Person" ;
    skos:definition "A human agent." ;
    rdfs:subClassOf ex:Agent .

ex:Organization a owl:Class ;
    rdfs:label "Organization" ;
    rdfs:comment "A group of agents." .

ex:Employee a owl:Class ;
    rdfs:label "Employee" ;
    rdfs:subClassOf ex:Person ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty ex:worksFor ;
        owl:someValuesFrom ex:Organization
    ] .

ex:worksFor a owl:ObjectProperty ;
    rdfs:domain ex:Person ;
    rdfs:range ex:Organization .
"""

# Richer ontology with two hierarchy branches for structural similarity tests.
#
#   Agent
#     ├── Person ──worksFor──▶ Organization
#     │     ├── Employee                         (branch A)
#     │     │     └── Manager
#     │     └── Contractor
#     └── SoftwareAgent                          (branch B)
#           └── Chatbot
#
#   Organization
#     └── Company
#
RICH_TTL = f"""\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex: <{EX}> .

ex:Agent a owl:Class ;
    rdfs:label "Agent" ;
    skos:definition "An entity that acts on its environment." .

ex:Person a owl:Class ;
    rdfs:label "Person" ;
    skos:definition "A human agent." ;
    rdfs:subClassOf ex:Agent .

ex:Employee a owl:Class ;
    rdfs:label "Employee" ;
    skos:definition "A person employed by an organization." ;
    rdfs:subClassOf ex:Person ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty ex:worksFor ;
        owl:someValuesFrom ex:Organization
    ] .

ex:Manager a owl:Class ;
    rdfs:label "Manager" ;
    skos:definition "An employee who manages others." ;
    rdfs:subClassOf ex:Employee .

ex:Contractor a owl:Class ;
    rdfs:label "Contractor" ;
    skos:definition "A person who works under contract." ;
    rdfs:subClassOf ex:Person .

ex:SoftwareAgent a owl:Class ;
    rdfs:label "Software Agent" ;
    skos:definition "An autonomous software entity." ;
    rdfs:subClassOf ex:Agent .

ex:Chatbot a owl:Class ;
    rdfs:label "Chatbot" ;
    skos:definition "A software agent that converses." ;
    rdfs:subClassOf ex:SoftwareAgent .

ex:Organization a owl:Class ;
    rdfs:label "Organization" ;
    skos:definition "A structured group of agents." .

ex:Company a owl:Class ;
    rdfs:label "Company" ;
    skos:definition "A commercial organization." ;
    rdfs:subClassOf ex:Organization .

ex:worksFor a owl:ObjectProperty ;
    rdfs:domain ex:Person ;
    rdfs:range ex:Organization .
"""


# --- Taxonomy projection tests ---


class TestTaxonomyProjection:
    def test_subclass_edges(self):
        graph = project_ontology(
            _backend(TAXONOMY_TTL), bidirectional_taxonomy=False, include_literals=False
        )
        edges = graph.edges
        assert (f"{EX}Dog", SUBCLASS_OF, f"{EX}Mammal") in edges
        assert (f"{EX}Mammal", SUBCLASS_OF, f"{EX}Animal") in edges
        assert (f"{EX}Cat", SUBCLASS_OF, f"{EX}Mammal") in edges

    def test_bidirectional_taxonomy(self):
        graph = project_ontology(
            _backend(TAXONOMY_TTL), bidirectional_taxonomy=True, include_literals=False
        )
        edges = graph.edges
        # Forward
        assert (f"{EX}Dog", SUBCLASS_OF, f"{EX}Mammal") in edges
        # Reverse
        assert (f"{EX}Mammal", SUPERCLASS_OF, f"{EX}Dog") in edges
        assert (f"{EX}Animal", SUPERCLASS_OF, f"{EX}Mammal") in edges

    def test_no_owl_thing_edges(self):
        """owl:Thing should be excluded from taxonomy edges."""
        ttl = f"""\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <{EX}> .

ex:A a owl:Class ; rdfs:label "A" ; rdfs:subClassOf owl:Thing .
"""
        graph = project_ontology(
            _backend(ttl), bidirectional_taxonomy=False, include_literals=False
        )
        for s, p, o in graph.edges:
            assert "owl#Thing" not in o

    def test_classes_collected(self):
        graph = project_ontology(
            _backend(TAXONOMY_TTL), include_literals=False
        )
        assert f"{EX}Animal" in graph.classes
        assert f"{EX}Mammal" in graph.classes
        assert f"{EX}Dog" in graph.classes
        assert f"{EX}Cat" in graph.classes


# --- Restriction projection tests ---


class TestRestrictionProjection:
    def test_somevaluesfrom(self):
        graph = project_ontology(
            _backend(RESTRICTION_TTL), bidirectional_taxonomy=False, include_literals=False
        )
        # Fish livesIn Habitat
        assert (f"{EX}Fish", f"{EX}livesIn", f"{EX}Habitat") in graph.edges

    def test_restriction_plus_taxonomy(self):
        graph = project_ontology(
            _backend(RESTRICTION_TTL), bidirectional_taxonomy=False, include_literals=False
        )
        # Both taxonomy and restriction edges present
        assert (f"{EX}Fish", SUBCLASS_OF, f"{EX}Animal") in graph.edges
        assert (f"{EX}Fish", f"{EX}livesIn", f"{EX}Habitat") in graph.edges


# --- Domain + Range projection tests ---


class TestDomainRangeProjection:
    def test_domain_range_edge(self):
        graph = project_ontology(
            _backend(DOMAIN_RANGE_TTL), bidirectional_taxonomy=False, include_literals=False
        )
        assert (f"{EX}Person", f"{EX}worksFor", f"{EX}Company") in graph.edges


# --- Equivalence projection tests ---


class TestEquivalenceProjection:
    def test_atomic_equivalence(self):
        graph = project_ontology(
            _backend(EQUIVALENCE_TTL), bidirectional_taxonomy=False, include_literals=False
        )
        # Bidirectional subClassOf from equivalence
        assert (f"{EX}Human", SUBCLASS_OF, f"{EX}Person") in graph.edges
        assert (f"{EX}Person", SUBCLASS_OF, f"{EX}Human") in graph.edges

    def test_complex_equivalence(self):
        graph = project_ontology(
            _backend(COMPLEX_EQUIV_TTL), bidirectional_taxonomy=False, include_literals=False
        )
        # Named class in intersection -> subClassOf
        assert (f"{EX}WildAnimal", SUBCLASS_OF, f"{EX}Animal") in graph.edges
        # Restriction in intersection -> property edge
        assert (f"{EX}WildAnimal", f"{EX}livesIn", f"{EX}Habitat") in graph.edges


# --- Annotation projection tests ---


class TestAnnotationProjection:
    def test_literal_edges(self):
        graph = project_ontology(
            _backend(ANNOTATION_TTL), bidirectional_taxonomy=False, include_literals=True
        )
        assert graph.literal_edge_count() > 0
        # Should have label and definition edges
        literal_preds = {p for _, p, _ in graph.literal_edges}
        assert "http://www.w3.org/2000/01/rdf-schema#label" in literal_preds
        assert "http://www.w3.org/2004/02/skos/core#definition" in literal_preds

    def test_no_literals_when_disabled(self):
        graph = project_ontology(
            _backend(ANNOTATION_TTL), include_literals=False
        )
        assert graph.literal_edge_count() == 0


# --- Combined ontology tests ---


class TestCombinedProjection:
    def test_all_rules_fire(self):
        graph = project_ontology(
            _backend(COMBINED_TTL), bidirectional_taxonomy=True, include_literals=True
        )
        edges = graph.edges

        # Taxonomy
        assert (f"{EX}Person", SUBCLASS_OF, f"{EX}Agent") in edges
        assert (f"{EX}Employee", SUBCLASS_OF, f"{EX}Person") in edges
        # Reverse taxonomy
        assert (f"{EX}Agent", SUPERCLASS_OF, f"{EX}Person") in edges

        # Restriction: Employee worksFor Organization
        assert (f"{EX}Employee", f"{EX}worksFor", f"{EX}Organization") in edges

        # Domain+Range: Person worksFor Organization
        assert (f"{EX}Person", f"{EX}worksFor", f"{EX}Organization") in edges

        # Annotations
        assert graph.literal_edge_count() > 0

    def test_edge_counts(self):
        graph = project_ontology(
            _backend(COMBINED_TTL), bidirectional_taxonomy=True, include_literals=True
        )
        assert graph.edge_count() > 0
        assert graph.literal_edge_count() > 0
        assert len(graph.classes) == 4


# --- Adjacency and walk tests ---


class TestAdjacencyAndWalks:
    def test_build_adjacency(self):
        graph = project_ontology(
            _backend(TAXONOMY_TTL), bidirectional_taxonomy=True, include_literals=False
        )
        adj = build_adjacency(graph)
        # Dog should be able to reach Mammal
        neighbors = adj.get(f"{EX}Dog", [])
        neighbor_nodes = [n for _, n in neighbors]
        assert f"{EX}Mammal" in neighbor_nodes

        # Mammal should reach both Dog (superClassOf) and Animal (subClassOf)
        mammal_neighbors = adj.get(f"{EX}Mammal", [])
        mammal_nodes = [n for _, n in mammal_neighbors]
        assert f"{EX}Animal" in mammal_nodes
        assert f"{EX}Dog" in mammal_nodes or f"{EX}Cat" in mammal_nodes

    def test_random_walks_length(self):
        graph = project_ontology(
            _backend(TAXONOMY_TTL), bidirectional_taxonomy=True, include_literals=False
        )
        adj = build_adjacency(graph)
        walks = random_walks(adj, num_walks=5, walk_length=10, rng_seed=42)

        assert len(walks) > 0
        # Each walk starts with a seed node
        for walk in walks:
            assert walk[0] in adj or walk[0] in {f"{EX}Animal", f"{EX}Mammal", f"{EX}Dog", f"{EX}Cat"}
            # Walk length: 1 (seed) + up to walk_length * 2 (pred + node per hop)
            assert len(walk) >= 1

    def test_random_walks_reproducible(self):
        graph = project_ontology(
            _backend(TAXONOMY_TTL), bidirectional_taxonomy=True, include_literals=False
        )
        adj = build_adjacency(graph)
        walks1 = random_walks(adj, num_walks=5, walk_length=10, rng_seed=42)
        walks2 = random_walks(adj, num_walks=5, walk_length=10, rng_seed=42)
        assert walks1 == walks2

    def test_walks_contain_predicates(self):
        """Walks should interleave entities and predicates."""
        graph = project_ontology(
            _backend(TAXONOMY_TTL), bidirectional_taxonomy=True, include_literals=False
        )
        adj = build_adjacency(graph)
        walks = random_walks(adj, num_walks=3, walk_length=5, rng_seed=42)

        for walk in walks:
            if len(walk) >= 3:
                # Position 1 should be a predicate (subClassOf or superClassOf)
                assert walk[1] in (SUBCLASS_OF, SUPERCLASS_OF)


# --- Word2Vec training tests ---


class TestEmbeddings:
    @pytest.fixture(autouse=True)
    def _check_gensim(self):
        pytest.importorskip("gensim")

    def test_train_embeddings(self):
        from ontoquery.owl2vec import train_embeddings

        graph = project_ontology(
            _backend(TAXONOMY_TTL), bidirectional_taxonomy=True, include_literals=False
        )
        adj = build_adjacency(graph)
        walks = random_walks(adj, num_walks=10, walk_length=20, rng_seed=42)

        model = train_embeddings(walks, vector_size=50, epochs=5)

        # All class URIs should have embeddings
        for cls in graph.classes:
            assert cls in model.wv, f"Missing embedding for {cls}"

    def test_get_class_embeddings(self):
        from ontoquery.owl2vec import get_class_embeddings, train_embeddings

        graph = project_ontology(
            _backend(TAXONOMY_TTL), bidirectional_taxonomy=True, include_literals=False
        )
        adj = build_adjacency(graph)
        walks = random_walks(adj, num_walks=10, walk_length=20, rng_seed=42)
        model = train_embeddings(walks, vector_size=50, epochs=5)

        embeddings = get_class_embeddings(model, graph.classes)
        assert len(embeddings) == len(graph.classes)
        for uri, vec in embeddings.items():
            assert len(vec) == 50

    def test_owl2vec_embed_end_to_end(self):
        from ontoquery.owl2vec import owl2vec_embed

        backend = _backend(COMBINED_TTL)
        embeddings, graph = owl2vec_embed(
            backend,
            num_walks=10,
            walk_length=20,
            vector_size=50,
            epochs=5,
        )
        assert len(embeddings) > 0
        assert len(graph.classes) == 4
        for uri, vec in embeddings.items():
            assert len(vec) == 50
            assert uri in graph.classes

    @pytest.fixture()
    def rich_embeddings(self):
        """Embed the rich ontology once, reuse across structural tests."""
        from ontoquery.owl2vec import owl2vec_embed

        backend = _backend(RICH_TTL)
        embeddings, graph = owl2vec_embed(
            backend,
            num_walks=80,
            walk_length=40,
            vector_size=100,
            epochs=30,
        )
        return embeddings

    @staticmethod
    def _cosine(a, b):
        import numpy as np

        a, b = np.array(a), np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def _sim(self, embeddings, name_a, name_b):
        return self._cosine(embeddings[f"{EX}{name_a}"], embeddings[f"{EX}{name_b}"])

    def test_parent_child_closer_than_cross_branch(self, rich_embeddings):
        """Employee↔Person (parent-child) > Employee↔SoftwareAgent (different branch)."""
        sim_close = self._sim(rich_embeddings, "Employee", "Person")
        sim_far = self._sim(rich_embeddings, "Employee", "SoftwareAgent")
        assert sim_close > sim_far, (
            f"Employee-Person ({sim_close:.3f}) should be > "
            f"Employee-SoftwareAgent ({sim_far:.3f})"
        )

    def test_siblings_closer_than_cross_branch(self, rich_embeddings):
        """Employee↔Contractor (siblings under Person) > Employee↔Chatbot (different branch)."""
        sim_sibling = self._sim(rich_embeddings, "Employee", "Contractor")
        sim_cross = self._sim(rich_embeddings, "Employee", "Chatbot")
        assert sim_sibling > sim_cross, (
            f"Employee-Contractor ({sim_sibling:.3f}) should be > "
            f"Employee-Chatbot ({sim_cross:.3f})"
        )

    def test_direct_parent_closer_than_grandparent(self, rich_embeddings):
        """Manager↔Employee (1 hop) > Manager↔Agent (3 hops)."""
        sim_parent = self._sim(rich_embeddings, "Manager", "Employee")
        sim_grandparent = self._sim(rich_embeddings, "Manager", "Agent")
        assert sim_parent > sim_grandparent, (
            f"Manager-Employee ({sim_parent:.3f}) should be > "
            f"Manager-Agent ({sim_grandparent:.3f})"
        )

    def test_same_branch_closer_than_property_target(self, rich_embeddings):
        """Employee↔Person (hierarchy) > Employee↔Organization (property link only)."""
        sim_hierarchy = self._sim(rich_embeddings, "Employee", "Person")
        sim_property = self._sim(rich_embeddings, "Employee", "Organization")
        assert sim_hierarchy > sim_property, (
            f"Employee-Person ({sim_hierarchy:.3f}) should be > "
            f"Employee-Organization ({sim_property:.3f})"
        )

    def test_branch_b_internal_coherence(self, rich_embeddings):
        """SoftwareAgent↔Chatbot (branch B parent-child) > SoftwareAgent↔Employee (cross-branch)."""
        sim_branch_b = self._sim(rich_embeddings, "SoftwareAgent", "Chatbot")
        sim_cross = self._sim(rich_embeddings, "SoftwareAgent", "Employee")
        assert sim_branch_b > sim_cross, (
            f"SoftwareAgent-Chatbot ({sim_branch_b:.3f}) should be > "
            f"SoftwareAgent-Employee ({sim_cross:.3f})"
        )

    def test_org_subtree_coherence(self, rich_embeddings):
        """Company↔Organization (parent-child) > Company↔Person (unrelated)."""
        sim_parent = self._sim(rich_embeddings, "Company", "Organization")
        sim_unrelated = self._sim(rich_embeddings, "Company", "Person")
        assert sim_parent > sim_unrelated, (
            f"Company-Organization ({sim_parent:.3f}) should be > "
            f"Company-Person ({sim_unrelated:.3f})"
        )
