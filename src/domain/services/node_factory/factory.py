from src.domain.models.common.node import NodeType,Node,StructureNode,ArticleElementNode,ArticleNode


class NodeFactory:
    def __init__(self):
        self.next_node_id = 1
        self.structure_names = (NodeType.LIBRO,NodeType.TITULO,NodeType.CAPITULO,NodeType.SECCION,NodeType.SUBSECCION,NodeType.DISPOSICION,NodeType.ROOT)
        self.article_names = (NodeType.ARTICULO, NodeType.ARTICULO_UNICO, NodeType.ANEXO)
        self.article_element_names = (NodeType.PARRAFO, NodeType.APARTADO_NUMERICO, NodeType.APARTADO_ALFA, NodeType.ORDINAL_NUMERICO, NodeType.ORDINAL_ALFA)
    
        self.article_element_registery = map
        
    def create_node(self, parent: Node, node_type:NodeType, name: str, level:int, content:str =None, prefix:str=None) -> Node:
        if node_type in self.structure_names:
            cls = StructureNode
        elif node_type in self.article_names:
            cls = ArticleNode
        elif node_type in self.article_element_names:
            cls = ArticleElementNode
        else:
            cls = Node

        # Generate unique ID content
        node_id = f"{prefix}_{self.next_node_id}" if prefix else self.next_node_id

        node = cls(
            id  = node_id,
            parent=parent,
            node_type=node_type,
            name=name,
            level=level,
            content=content or [],
        )

        
        if parent:
            parent.add_child(node)

        self.next_node_id += 1

        return node
