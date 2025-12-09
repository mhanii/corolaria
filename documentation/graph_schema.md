# Coloraria Graph Schema Documentation

## Overview

Coloraria uses **Neo4j** as its graph database to store Spanish legal documents (normativas) with their hierarchical structure, metadata, and change history. The graph model enables:

- **Semantic search** via vector embeddings on articles
- **Version tracking** to see how articles evolved over time
- **Change attribution** to identify which laws modified which articles
- **Hierarchical navigation** from law → titles → chapters → articles

---

## Node Types

### Primary Nodes

| Node Label | Description | Key Properties |
|------------|-------------|----------------|
| `Normativa` | A legal document (law, constitution, decree) | `id`, `titulo`, `fecha_vigencia`, `fecha_publicacion`, `url_eli` |
| `articulo` | An article within a law | `id`, `name`, `full_text`, `embedding`, `path`, `fecha_vigencia`, `fecha_caducidad` |

> [!NOTE]
> Structural nodes (Libro, Título, Capítulo, Sección) are **not stored** in the graph to reduce database size.
> Instead, the `path` property on articles preserves the hierarchy (e.g., `"Libro I, Titulo II, Capitulo I"`).

### Content Elements (within Articles)

| Node Label | Description |
|------------|-------------|
| `apartado_numerico` | Numbered paragraph (1, 2, 3...) |
| `apartado_alfa` | Lettered paragraph (a, b, c...) |
| `parrafo` | Plain text paragraph |


### Metadata Nodes

| Node Label | Description | Example |
|------------|-------------|---------|
| `Materia` | Subject matter/topic | `CONSTITUCION_ESPANOLA`, `DERECHO_LABORAL` |
| `Departamento` | Issuing government body | `CORTES_GENERALES`, `MINISTERIO_DE_JUSTICIA` |
| `Rango` | Legal rank/type | `CONSTITUCION`, `LEY_ORGANICA`, `REAL_DECRETO` |

### Change Tracking Nodes

| Node Label | Description | Key Properties |
|------------|-------------|----------------|
| `ChangeEvent` | Records modifications to a law | `id`, `source_document_id`, `target_document_id`, `affected_nodes_count` |

---

## Relationship Types

### Hierarchical Structure

```
Article -[:PART_OF]-> Normativa
ArticleElement -[:PART_OF]-> Article
```

Articles connect directly to their parent `Normativa` via `PART_OF`. Article elements (apartados, párrafos) connect to their parent article.

**Example:**
```
(apartado_numerico: "1") -[:PART_OF]-> (articulo: "Art. 1") -[:PART_OF]-> (Normativa: "Constitución")
```


### Version Chains

```
Old_article -[:NEXT_VERSION]-> New_article
New_article -[:PREVIOUS_VERSION]-> Old_article
```

When a law is modified, the affected article gets a new version. The `NEXT_VERSION` relationship links versions chronologically.

### Metadata Relationships

```
Normativa -[:ABOUT]-> Materia        # Subject matter classification
Normativa -[:ISSUED_BY]-> Departamento   # Issuing authority
Normativa -[:HAS_RANK]-> Rango       # Legal hierarchy rank
```

### Change Tracking

```
SourceNormativa -[:INTRODUCED_CHANGE]-> ChangeEvent
ChangeEvent -[:MODIFIES]-> TargetNormativa
ChangeEvent -[:CHANGED {type}]-> Article
```

| Relationship | Direction | Description |
|--------------|-----------|-------------|
| `INTRODUCED_CHANGE` | Source → ChangeEvent | The law that caused the modification |
| `MODIFIES` | ChangeEvent → Target | The law being modified |
| `CHANGED` | ChangeEvent → Article | Specific article affected |

The `CHANGED` relationship has a `type` property:
- `"added"` - New content added
- `"modified"` - Existing content changed
- `"removed"` - Content deleted

### Citation & Reference Relationships

```
article -[:REFERS_TO]-> article   # Article citing another article
article -[:REFERS_TO]-> Normativa # Article citing a law (no specific article)
article -[:CITES]-> Normativa    # Judicial citation (future)
article -[:DEROGATES]-> article  # When "DEROGA" appears in context
article -[:MODIFIES]-> article   # When "MODIFICA" appears in context
```

| Relationship | Direction | Description |
|--------------|-----------|-------------|
| `REFERS_TO` | Article → Article/Normativa | Generic legal reference |
| `CITES` | Article → Judicial Decision | Citation of court ruling |
| `DEROGATES` | Article → Article | Explicit derogation |
| `MODIFIES` | Article → Article | Explicit modification |

**Properties on REFERS_TO:**
- `raw_citation` - Original text that triggered the link
- `created_at` - When the link was created


---

## Example: Spanish Constitution

The Spanish Constitution (`BOE-A-1978-31229`) in the graph:

```
(Normativa {
  id: "BOE-A-1978-31229",
  titulo: "Constitución Española",
  fecha_vigencia: 19781229,
  fecha_publicacion: 19781229
})
  -[:ABOUT]-> (Materia {name: "CONSTITUCION_ESPANOLA"})
  -[:ISSUED_BY]-> (Departamento {name: "CORTES_GENERALES"})
  -[:HAS_RANK]-> (Rango {name: "CONSTITUCION"})
```

### Content Hierarchy Example

```
Normativa: "Constitución Española"
├── Articulo: "1" (path: "Titulo PRELIMINAR")
│   ├── apartado_numerico: "1" → "España se constituye en un Estado social..."
│   ├── apartado_numerico: "2" → "La soberanía nacional reside..."
│   └── apartado_numerico: "3" → "La forma política del Estado..."
├── Articulo: "2" (path: "Titulo PRELIMINAR")
├── Articulo: "11" (path: "Titulo I, Capitulo PRIMERO")
└── ...
```


### Change Tracking Example

The Constitution has been modified 3 times:

```
(Normativa: "BOE-A-1992-20403") -[:INTRODUCED_CHANGE]-> (ChangeEvent)
    ↓
(ChangeEvent) -[:MODIFIES]-> (Normativa: "BOE-A-1978-31229")
    ↓
(ChangeEvent) -[:CHANGED {type: "modified"}]-> (articulo: "13")
```

---

## Vector Index

A vector index exists on article embeddings for semantic search:

```cypher
CREATE VECTOR INDEX article_embeddings IF NOT EXISTS
FOR (n:articulo) ON (n.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 768,
  `vector.similarity_function`: 'cosine'
}}
```

### Usage

```cypher
CALL db.index.vector.queryNodes('article_embeddings', 10, $query_vector)
YIELD node, score
RETURN node.full_text, score
ORDER BY score DESC
```

---

## Key Queries

### Find all articles in a law
```cypher
MATCH (a:articulo)-[:PART_OF*]->(n:Normativa {id: $normativa_id})
RETURN a.name, a.full_text
```

### Get article version history
```cypher
MATCH path = (a:articulo {id: $article_id})-[:NEXT_VERSION*]->()
RETURN [node in nodes(path) | node.fecha_vigencia] as versions
```

### Find changes to a law
```cypher
MATCH (e:ChangeEvent)-[:MODIFIES]->(n:Normativa {id: $normativa_id})
MATCH (source)-[:INTRODUCED_CHANGE]->(e)
MATCH (e)-[r:CHANGED]->(article)
RETURN source.id, r.type, article.name
```
