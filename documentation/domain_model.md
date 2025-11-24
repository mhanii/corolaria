# Domain Model

## Overview
Coloraria follows **Domain-Driven Design (DDD)** principles to model legal concepts. The domain layer is the heart of the application, independent of the database or UI.

**Location**: `src/domain/`

## Core Aggregates & Entities

### 1. Normativa (`NormativaCons`)
*   **Type**: Aggregate Root.
*   **Description**: Represents a consolidated law (a law with all its amendments applied).
*   **Attributes**:
    *   `id`: Unique identifier (e.g., BOE ID).
    *   `metadata`: `Metadata` value object.
    *   `content_tree`: The root node of the structural tree.

### 2. The Document Tree (`Node`)
*   **Base Class**: `src/domain/models/common/node.py`
*   **Subclasses**:
    *   `ArticleNode`: Represents a legal article. Holds the `text` and `embedding`.
    *   `StructureNode`: Represents structural containers like Books, Titles, Chapters.
*   **Behavior**: Nodes know their children and their type (`NodeType`).

### 3. Value Objects
*   **Metadata**: Contains immutable properties like `fecha_publicacion`, `rango` (rank), `departamento`.
*   **Analysis**: Contains references to other laws (`referencias_anteriores`, `referencias_posteriores`) and subject matter tags (`materias`).
*   **Version**: Represents a specific temporal version of an article (used during processing).

## Services

### TreeBuilder
*   **Location**: `src/domain/services/tree_builder.py`
*   **Role**: Responsible for parsing the flat list of text blocks from the source and assembling them into the hierarchical `Node` tree. It handles the logic of "opening" and "closing" structural levels (e.g., when a new Title starts, the previous Chapter ends).
