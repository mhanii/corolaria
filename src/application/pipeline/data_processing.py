from src.domain.models.common.metadata import Metadata
from src.domain.models.common.analysis import Analysis
from src.domain.models.common.block import Block
from src.domain.models.common.version import Version
from src.domain.models.common.element import Element
from src.domain.models.common.referencia import Referencia

from src.domain.value_objects.rangos_model import Rangos
from src.domain.value_objects.estados_consolidacion_model import EstadosConsolidacion
from src.domain.value_objects.relaciones_anteriores_model import RelacionesAnteriores
from src.domain.value_objects.relaciones_posteriores_model import RelacionesPosteriores
from src.domain.value_objects.departamentos_model import Departamentos
from src.domain.value_objects.ambitos_model import Ambitos
from src.domain.value_objects.materias_model import Materias

from src.domain.services.tree_builder import TreeBuilder
from src.domain.models.common.base import Ambito, Materia, Departamento, Rango, EstadoConsolidacion, ReferenciaType, BlockType,ElementType

from src.domain.models.normativa import NormativaCons
from src.domain.services.utils.print_tree import print_tree
from .base import Step
import re
from src.utils.logger import output_logger



class DataProcessor(Step):
    def __init__(self, name: str, *args): # For now you must specify the id.
        super().__init__(name)

        self.content_tree = TreeBuilder("root")
        self.prohibited_types = {"nota_inicial", "nota_final","nota", "firma", "indice", "portada"}
        



        
    def preprocessing(self, content):
        """
        Preprocess content to distribute compound article block content to existing individual articles.
        E.g., "Artículos 638 y 639" with "(Derogados)" finds existing Art. 638 and 639 blocks
        and adds the derogation info to them.
        """
        patterns = [
            # Match "Artículos X a Y" (range)
            (
                'range',
                re.compile(r'^Artículos?\s+(\d+)\s+a\s+(\d+)(?:\s*\.)?$', re.I)
            ),
            # Match "Artículos X, Y, ... y Z" (list)
            (
                'list',
                re.compile(r'^Artículos?\s+((?:\d+(?:\s*,\s*)?)+)\s+y\s+(\d+)(?:\s*\.)?$', re.I)
            ),
            # Match "Artículos X y Y" (simple pair)
            (
                'pair',
                re.compile(r'^Artículos?\s+(\d+)\s+y\s+(\d+)(?:\s*\.)?$', re.I)
            ),
        ]
        
        blocks = content.get("bloque", [])
        
        # Build index of existing individual article blocks
        article_index = {}  # {article_num: block_dict}
        compound_blocks = []  # Blocks to remove after processing
        
        for block in blocks:
            title = block.get("@titulo", "").strip()
            
            # Check if this is a single article block
            single_match = re.match(r'^Artículo\s+(\d+)(?:\s+\w+)?(?:\s*\.)?$', title, re.I)
            if single_match:
                article_num = int(single_match.group(1))
                article_index[article_num] = block
        
        # Now process compound blocks
        for block in blocks:
            title = block.get("@titulo", "").strip()
            
            for pattern_type, pattern in patterns:
                match = pattern.match(title)
                
                if match:
                    compound_blocks.append(block)
                    article_nums = []
                    
                    if pattern_type == 'range':
                        # Handle range: "Artículos 633 a 637"
                        start = int(match.group(1))
                        end = int(match.group(2))
                        article_nums = list(range(start, end + 1))
                        output_logger.info(f"  📦 Found compound range: {title} → Articles {start} to {end}")
                        
                    elif pattern_type == 'list':
                        # Handle list: "Artículos 638, 639 y 640"
                        first_nums = match.group(1)
                        last_num = match.group(2)
                        article_nums = [int(n.strip()) for n in first_nums.split(',')]
                        article_nums.append(int(last_num))
                        output_logger.info(f"  📦 Found compound list: {title} → Articles {', '.join(map(str, article_nums))}")
                        
                    elif pattern_type == 'pair':
                        # Handle pair: "Artículos 638 y 639"
                        article_nums = [int(match.group(1)), int(match.group(2))]
                        output_logger.info(f"  📦 Found compound pair: {title} → Articles {', '.join(map(str, article_nums))}")
                    
                    # Distribute this compound block's content to individual articles
                    self._distribute_to_articles(block, article_nums, article_index)
                    break
        
        # Remove compound blocks from the list
        content["bloque"] = [b for b in blocks if b not in compound_blocks]
        
        return content


    def _distribute_to_articles(self, compound_block: dict, article_nums: list, article_index: dict):
        """
        Distribute content from a compound block to existing individual article blocks.
        
        Args:
            compound_block: The compound block (e.g., "Artículos 638 y 639")
            article_nums: List of article numbers to distribute to
            article_index: Dictionary mapping article numbers to their blocks
        """
        import copy
        
        # Get the versions from the compound block
        compound_versions = compound_block.get("version", [])
        
        for article_num in article_nums:
            if article_num not in article_index:
                output_logger.warning(f"  ⚠️  Warning: Article {article_num} not found in existing blocks!")
                continue
            
            target_block = article_index[article_num]
            
            existing_versions = target_block.get("version", [])
            
            for compound_version in compound_versions:
                version_copy = copy.deepcopy(compound_version)
                
                compound_p = version_copy.get("p", None)
                if compound_p:
                    if isinstance(compound_p, list) and len(compound_p) > 0:
                        version_copy["p"][0] = f"Artículo {article_num}."
                    elif isinstance(compound_p, str):
                        version_copy["p"] = f"Artículo {article_num}."
                
                existing_versions.append(version_copy)
                output_logger.info(f"    ✓ Added new version to Article {article_num}")
            
            target_block["version"] = existing_versions

    def process_metadata(self, metadata):
        fecha_actualizacion = metadata.get("fecha_actualizacion", None)
        id = metadata.get("identificador", None)
        ambito = Ambito(Ambitos.from_string(metadata.get("ambito", None)))
        departamento = Departamento(Departamentos.from_string(metadata.get("departamento", None)))
        rango = Rango(Rangos.from_string(metadata.get("rango", None)))
        fecha_disposicion = metadata.get("fecha_disposicion", None)
        titulo = metadata.get("titulo", None)
        diario = metadata.get("diario", None)
        fecha_publicacion = metadata.get("fecha_publicacion", None)
        diario_numero = metadata.get("diario_numero", None)
        fecha_vigencia = metadata.get("fecha_vigencia", None)
        vigencia_agotada = metadata.get("vigencia_agotada", None)
        estatus_derogacion = metadata.get("estatus_derogacion", None)
        estatus_anulacion = metadata.get("estatus_anulacion", None)
        estado_consolidacion = EstadoConsolidacion(EstadosConsolidacion.from_string(metadata.get("estado_consolidacion", None)))
        url_eli = metadata.get("url_eli", None)
        url_html_consolidada = metadata.get("url_html_consolidada", None)


        return Metadata(
            fecha_actualizacion=fecha_actualizacion,
            id=id,
            ambito=ambito,
            departamento=departamento,
            titulo=titulo,
            rango=rango,
            fecha_disposicion=fecha_disposicion,
            diario=diario,
            fecha_publicacion=fecha_publicacion,
            diario_numero=diario_numero,
            fecha_vigencia=fecha_vigencia,
            estatus_derogacion=estatus_derogacion,
            estatus_anulacion=estatus_anulacion,
            vigencia_agotada=vigencia_agotada,
            estado_consolidacion=estado_consolidacion,
            url_eli=url_eli,
            url_html_consolidado=url_html_consolidada
        )
    def process_analysis(self, analysis):

        materias = [Materia(Materias.from_string(materia_str)) for materia_str in analysis.get("materias", [])]

        referencias = analysis.get("referencias", [])

        ref_anteriores = [Referencia(id_norma=ref.get("id_norma",None),type=ReferenciaType.ANTERIOR,relacion=RelacionesAnteriores.from_string(ref.get("relacion",None)),text=ref.get("texto")) for ref in referencias.get("anteriores", [])]
        ref_posteriores = [Referencia(id_norma=ref.get("id_norma",None),type=ReferenciaType.POSTERIOR,relacion=RelacionesPosteriores.from_string(ref.get("relacion",None)),text=ref.get("texto")) for ref in referencias.get("posteriores", [])]
        
        return Analysis(
            materias=materias,
            referencias_anteriores=ref_anteriores,
            referencias_posteriores=ref_posteriores
        )
    
    def process_content(self, content):
        blocks = content.get("bloque", [])

        for block in blocks:
            id = block.get("@id", None)
            type = BlockType(block.get("@tipo", None).lower())
            title = block.get("@titulo", None)

            if type in self.prohibited_types:
                continue
            
            versions = [self.process_version(version) for version in block.get("version", [])]
            
            self.content_tree.parse_versions(versions)



    
    def process_version(self, version) -> Version:
        id_norma = version.get("@id_norma", None)
        fecha_publicacion = version.get("@fecha_publicacion", None)
        fecha_vigencia = version.get("@fecha_vigencia", None)

        known_meta = {"@id_norma", "@fecha_publicacion", "@fecha_vigencia"}
        elements_by_tag = {}
        processed_elements = []
        for k, v in version.items():
            if k in known_meta or k.startswith("@"):
                continue
            items = v if isinstance(v, list) else [v]
            elements_by_tag[k] = items
            processed_elements += [Element(element_type=ElementType(k), content=item) for item in items]

        # dispatch to handler methods named process_<tag> when present
        # processed_elements = [Element(element_type=ElementType(tag), content=item) for item in items for tag, items in elements_by_tag.items()]
        version =  Version(
            id_norma=id_norma,
            fecha_publicacion=fecha_publicacion,
            fecha_vigencia=fecha_vigencia,
            content=processed_elements
        )

    
        return version

    def process(self, data):
        data = data.get("data", {})
        metadata = data.get("metadatos", {})
        analysis = data.get("analisis", {})
        content = data.get("texto", [])
        

        processed_metadata = self.process_metadata(metadata)
        processed_analysis = self.process_analysis(analysis)

        preprocessed_content = self.preprocessing(content=content)
        
        self.process_content(preprocessed_content)
        
        
        self.content_tree.change_handler.print_summary(verbose=True)
        print_tree(self.content_tree.root)
        normativa = NormativaCons(id=processed_metadata.id,metadata=processed_metadata,analysis=processed_analysis,content_tree=self.content_tree.root)
        change_events = self.content_tree.change_handler.change_events
        return normativa, change_events