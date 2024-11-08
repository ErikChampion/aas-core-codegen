"""Generate the OPC UA Schema node set corresponding to the meta-model."""
import collections
import io
import itertools
from typing import TextIO, Tuple, Optional, List, MutableMapping, Mapping
import xml.etree.ElementTree as ET
import xml.dom.minidom

from icontract import ensure

import aas_core_codegen.opcua
from aas_core_codegen import run, intermediate, specific_implementations
from aas_core_codegen.common import Stripped, Error, assert_never
import aas_core_codegen.opcua.naming as opcua_naming

assert aas_core_codegen.opcua.__doc__ == __doc__

_PRIMITIVE_MAP = {
    intermediate.PrimitiveType.BOOL: "Boolean",
    intermediate.PrimitiveType.INT: "Int64",
    intermediate.PrimitiveType.FLOAT: "Double",
    intermediate.PrimitiveType.STR: "String",
    intermediate.PrimitiveType.BYTEARRAY: "ByteString",
}
assert all(literal in _PRIMITIVE_MAP for literal in intermediate.PrimitiveType)


class IdentifierMachine:
    """Produce novel identifiers."""

    def __init__(self) -> None:
        self._next_identifier = 5000

    def next(self) -> int:
        """Return the current identifier, and increment for the next one."""
        result = self._next_identifier
        self._next_identifier += 1
        return result



def _generate_aliases(
        symbol_table: intermediate.SymbolTable,
        our_type_to_identifier: Mapping[intermediate.OurType, int]
) -> ET.Element:
    """Generate the aliases including the primitive values."""
    aliases = ET.Element("Aliases")

    for name, i in (
            ("Boolean", 1),
            ("Int64", 8),
            ("Double", 11),
            ("String", 12),
            ("ByteString", 15)
    ):
        alias = ET.Element("Alias", {"Alias": name})
        alias.text = f"i={i}"
        aliases.append(alias)

    for our_type in itertools.chain(
            symbol_table.enumerations,
            symbol_table.classes
    ):
        alias = ET.Element("Alias",
                           {"Alias": opcua_naming.data_type_name(our_type.name)})
        alias.text = f"ns=1;i={our_type_to_identifier[our_type]}"

        aliases.append(alias)

    return aliases

def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for child in elem:
            indent(child, level+1)
            if not child.tail or not child.tail.strip():
                child.tail = i + "  "
        if not child.tail or not child.tail.strip():
            child.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def _generate_for_enum(
    enum: intermediate.Enumeration,
    our_type_to_identifier: Mapping[intermediate.OurType, int],
) -> ET.Element:
    """Define a data type for the enumeration."""
    data_type_name = opcua_naming.data_type_name(enum.name)

    root = ET.Element(
        "UADataType",
        collections.OrderedDict(
            [
                ("NodeId", f"ns=1;i={our_type_to_identifier[enum]}"),
                ("BrowseName", f"1:{data_type_name}"),
            ]
        ),
    )

    # Adding DisplayName and Description
    display_name = ET.SubElement(root, "DisplayName")
    display_name.text = data_type_name

    description = ET.SubElement(root, "Description")
    description.text = f"Enumeration for {data_type_name}"

    # Adding Definition with fields
    definition = ET.SubElement(
        root,
        "Definition",
        {"Name": data_type_name, "IsUnion": "false"},
    )

    for literal in enum.literals:
        field = ET.SubElement(
            definition,
            "Field",
            {
                "Name": opcua_naming.enum_literal_name(literal.name),
                "Value": str(literal.value),
            },
        )
        # Optionally add DisplayName for each field
        field_display_name = ET.SubElement(field, "DisplayName")
        field_display_name.text = opcua_naming.enum_literal_name(literal.name)

    return root


def _generate_definition(
    cls: intermediate.ClassUnion,
    our_type_to_identifier: Mapping[intermediate.OurType, int],
    identifier_machine: IdentifierMachine,
) -> List[ET.Element]:
    """Generate the definition for the given class."""
    result = []

    data_type_name = opcua_naming.data_type_name(cls.name)

    # Create UADataType element
    data_type = ET.Element(
        "UADataType",
        {
            "NodeId": f"ns=1;i={our_type_to_identifier[cls]}",
            "BrowseName": f"1:{data_type_name}",
        },
    )

    # Add DisplayName and Description
    display_name = ET.SubElement(data_type, "DisplayName")
    display_name.text = data_type_name

    description = ET.SubElement(data_type, "Description")
    description.text = f"DataType for {data_type_name}"

    # References (inheritance)
    references = ET.SubElement(data_type, "References")
    has_subtype = ET.SubElement(
        references,
        "Reference",
        {"ReferenceType": "HasSubtype", "IsForward": "false"},
    )
    has_subtype.text = "i=22"  # BaseDataType

    # Add Definition
    definition = ET.SubElement(
        data_type,
        "Definition",
        {"Name": data_type_name, "IsUnion": "false"},
    )

    # Add Fields for each property
    for prop in cls.properties:
        field = ET.SubElement(definition, "Field", {"Name": prop.name})

        # Determine the data type of the field
        type_anno = intermediate.beneath_optional(prop.type_annotation)
        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
            primitive_type = _PRIMITIVE_MAP[type_anno.a_type]
            field.set("DataType", primitive_type)
        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.our_type, intermediate.Enumeration):
                field.set(
                    "DataType",
                    opcua_naming.data_type_name(type_anno.our_type.name),
                )
            elif isinstance(
                type_anno.our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
            ):
                field.set(
                    "DataType",
                    opcua_naming.data_type_name(type_anno.our_type.name),
                )
            else:
                # Handle other cases if necessary
                raise NotImplementedError(
                    f"Unsupported type: {type_anno.our_type}"
                )
        else:
            raise NotImplementedError(f"Unsupported type annotation: {type_anno}")

        # Handle optional fields
        # if intermediate.is_optional(prop.type_annotation):
        #     field.set("IsOptional", "true")
        # else:
        #     field.set("IsOptional", "false")

    result.append(data_type)
    return result



@ensure(lambda result: not (result[1] is not None) or (len(result[1]) >= 1))
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate(
        symbol_table: intermediate.SymbolTable,
        spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate tne node set according to the symbol table."""
    #Before:
    # base_nodeset_key = specific_implementations.ImplementationKey(
    #     "base_nodeset.xml"
    # )
    #
    # base_nodeset_text = spec_impls.get(base_nodeset_key, None)
    # if base_nodeset_text is None:
    #     return None, [
    #         Error(
    #             None,
    #             f"The implementation snippet for the base OPC UA nodeset "
    #             f"is missing: {base_nodeset_key}",
    #         )
    #     ]
    #
    # try:
    #     root = ET.fromstring(base_nodeset_text)
    # except Exception as err:
    #     return None, [
    #         Error(
    #             None,
    #             f"Failed to parse the base nodeset XML out of "
    #             f"the snippet {base_nodeset_key}: {err}",
    #         )
    #     ]

    # After:

    OPCUA_NS = "http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"
    ET.register_namespace('', OPCUA_NS)

    root = ET.Element('{%s}UANodeSet' % OPCUA_NS)

    namespace_uris = ET.SubElement(root, '{%s}NamespaceUris' % OPCUA_NS)
    uri_elem = ET.SubElement(namespace_uris, '{%s}Uri' % OPCUA_NS)
    uri_elem.text = 'https://dummy/198/4'  # Use your actual namespace URI

    models = ET.SubElement(root, '{%s}Models' % OPCUA_NS)
    model = ET.SubElement(models, '{%s}Model' % OPCUA_NS, {
        'ModelUri': 'https://dummy/198/4',  # Use your actual ModelUri
        'Version': 'V198.4',  # Use your actual version
        'PublicationDate': '2023-10-10T00:00:00Z'  # Use the correct date
    })
    required_model = ET.SubElement(model, '{%s}RequiredModel' % OPCUA_NS, {
        'ModelUri': 'http://opcfoundation.org/UA/',
        'Version': '1.04.3',
        'PublicationDate': '2019-09-09T00:00:00Z'
    })

    identifier_machine = IdentifierMachine()

    our_type_to_identifier = collections.OrderedDict(
    )  # type: MutableMapping[intermediate.OurType, int]
    for i, our_type in enumerate(
            itertools.chain(
                symbol_table.enumerations,
                symbol_table.classes,
            )
    ):
        our_type_to_identifier[our_type] = identifier_machine.next()

    aliases = _generate_aliases(
        symbol_table=symbol_table,
        our_type_to_identifier=our_type_to_identifier
    )

    root.append(aliases)

    for enum in symbol_table.enumerations:
        root.append(
            _generate_for_enum(
                enum=enum,
                our_type_to_identifier=our_type_to_identifier
            )
        )

    # for cls in symbol_table.concrete_classes:
    #     root.extend(
    #         _generate_definition(
    #         cls=cls,
    #         our_type_to_identifier=our_type_to_identifier,
    #         identifier_machine=identifier_machine)
    #     )

    # Generate definitions for classes
    for cls in symbol_table.classes:
        data_type_elements = _generate_definition(
            cls=cls,
            our_type_to_identifier=our_type_to_identifier,
            identifier_machine=identifier_machine,
        )
        root.extend(data_type_elements)

    # Indent for pretty-printing
    indent(root)

    # Convert to string
    xml_str = ET.tostring(root, encoding='utf-8')

    # Pretty-print
    dom = xml.dom.minidom.parseString(xml_str)
    pretty_xml_as_string = dom.toprettyxml(indent="  ")

    # Remove extra blank lines if necessary
    pretty_xml_as_string = '\n'.join([line for line in pretty_xml_as_string.split('\n') if line.strip()])

    return pretty_xml_as_string, None

    # text = ET.tostring(root, encoding="unicode", method="xml")
    #
    # # NOTE (mristin):
    # # This approach is slow, but effective. As long as the meta-model is not too big,
    # # this should work.
    # # noinspection PyUnresolvedReferences
    # pretty_text = xml.dom.minidom.parseString(text).toprettyxml(indent="  ")

    # return text, None


def execute(
        context: run.Context,
        stdout: TextIO,
        stderr: TextIO,
) -> int:
    """
    Execute the generation with the given parameters.

    Return the error code, or 0 if no errors.
    """
    code, errors = _generate(
        symbol_table=context.symbol_table,
        spec_impls=context.spec_impls
    )
    if errors is not None:
        run.write_error_report(
            message=f"Failed to generate the OPC UA node set "
                    f"based on {context.model_path}",
            errors=[context.lineno_columner.error_message(error) for error in errors],
            stderr=stderr,
        )
        return 1

    assert code is not None

    # noinspection SpellCheckingInspection
    pth = context.output_dir / "nodeset.xml"
    try:
        pth.write_text(code, encoding="utf-8")
    except Exception as exception:
        run.write_error_report(
            message=f"Failed to write the OPC UA node set to {pth}",
            errors=[str(exception)],
            stderr=stderr,
        )
        return 1

    stdout.write(f"Code generated to: {context.output_dir}\n")

    return 0
