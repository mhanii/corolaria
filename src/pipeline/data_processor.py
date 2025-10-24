from src.documents.normativa_cons import NormativaCons, Metadata, Analysis, Version, Block, Referencia,Element
from src.models.rangos_model import Rangos
from src.models.estados_consolidacion_model import EstadosConsolidacion
from src.models.relaciones_anteriores_model import RelacionesAnteriores
from src.models.relaciones_posteriores_model import RelacionesPosteriores
from src.models.departamentos_model import Departamentos
from src.models.ambitos_model import Ambitos
from src.models.materias_model import Materias
from src.documents.common import TreeBuilder
from src.documents.base import Ambito, Materia, Departamento, Rango, EstadoConsolidacion, ReferenciaType, BlockType,ElementType

from .base import Step

class DataProcessor(Step):
    def __init__(self, name: str, *args): # For now you must specify the id.
        super().__init__(name)

        self.content_tree = TreeBuilder()
        
    
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
        blocks_tag = content.get("bloque", [])
        blocks = [self.process_block(block) for block in blocks_tag]
        

        return blocks

    def process_block(self, block) -> Block:
        id = block.get("@id", None)
        type = BlockType(block.get("@tipo", None))
        title = block.get("@titulo", None)

        versions = [self.process_version(version) for version in block.get("version", [])]
        
        self.content_tree.parse_versions(versions)
        
        block = Block(
            id=id,
            type=type,
            title=title,
            versions=versions
        )


        return block
    
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
        processed_content = self.process_content(content)

        # self.content_tree.print_tree(show_versions=False)

        # Further processing can be done here for analysis and blocks
        return NormativaCons(id=processed_metadata.id,metadata=metadata,analysis=processed_analysis,blocks=processed_content)