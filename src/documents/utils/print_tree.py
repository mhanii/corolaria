from src.documents.node_factory.base import Node
import logging

output_logger = logging.getLogger("output_logger")

def print_tree(
    node: Node,
    prefix: str = "",
    is_last: bool = True,
):
    """Print the tree structure with proper formatting."""

    if node is None:
        return

    # Connector logic
    connector = "└─ " if is_last else "├─ "
    output_logger.info(f"{prefix}{connector}{node.get_full_name()}")

    # Prefix for children
    extension = "   " if is_last else "│  "
    new_prefix = prefix + extension

    items = node.content
    child_nodes = [item for item in items if isinstance(item, Node)]
    text_items = [item for item in items if isinstance(item, str)]

    # Print text content first
    for i, text_item in enumerate(text_items):
        is_last_item = (i == len(text_items) - 1) and (len(child_nodes) == 0)
        text_connector = "└─ " if is_last_item else "├─ "
        preview = text_item[:80] + "..." if len(text_item) > 80 else text_item
        output_logger.info(f'{new_prefix}{text_connector}"{preview}"')

    # Then print child nodes
    for i, item in enumerate(child_nodes):
        is_last_item = i == len(child_nodes) - 1
        print_tree(
            item,
            new_prefix,
            is_last_item,
        )
