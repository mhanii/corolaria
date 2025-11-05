from typing import Optional
from src.domain.models.common.node import Node
from datetime import datetime
from src.utils.logger import output_logger

def print_tree(
            node: Node = None,
            prefix: str = "",
            is_last: bool = True,
            target_date: Optional[str] = None
        ):
        """Print the tree structure with proper formatting."""


        connector = "└─ " if is_last else "├─ "
        extension = "   " if is_last else "│  "

        new_prefix = prefix + extension
        output_logger.info(f"{prefix}{connector}{node.get_full_name()}")

        items = node.content
        for i, item in enumerate(items):
            is_last_item = (i == len(items) - 1)

            if isinstance(item, Node):
                print_tree(
                    item, new_prefix, is_last_item,
                    target_date
                )
            else:
                text_connector = "└─ " if is_last_item else "├─ "
                preview = item[:80] + "..." if len(item) > 80 else item
                output_logger.info(f'{new_prefix}{text_connector}"{preview}"')
