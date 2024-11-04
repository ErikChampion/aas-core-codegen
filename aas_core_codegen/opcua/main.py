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


def _generate_for_enum(
        enum: intermediate.Enumeration,
        our_type_to_identifier: Mapping[intermediate.OurType, int]
) -> ET.Element:
    """Define a data type for the enumeration."""
    data_type_name = opcua_naming.data_type_name(enum.name)

    root = ET.Element(
        "UADataType",
        collections.OrderedDict(
            [
                ("NodeId", f"ns=1;i={our_type_to_identifier[enum]}"),
                ("BrowseName", f"1:{data_type_name}")
            ]
        )
    )

    # TODO (mristin, 2024-11-04): add DisplayName, References etc.

    definition = ET.Element("Definition")
    root.append(definition)

    for literal in enum.literals:
        field = ET.Element(
            "Field",
            collections.OrderedDict(
                [
                    ("Name", opcua_naming.enum_literal_name(literal.name)),
                    ("Value", literal.value)
                ]
            )
        )

        definition.append(field)

    return root


def _generate_definition(
        cls: intermediate.ClassUnion,
        our_type_to_identifier: Mapping[intermediate.OurType, int],
        identifier_machine: IdentifierMachine
) -> List[ET.Element]:
    """Generate the definition for the given class."""
    result = []  # type: List[ET.Element]

    if isinstance(cls, intermediate.ConcreteClass):
        # TODO (mristin, 2024-11-04): implement
        pass
    elif isinstance(cls, intermediate.AbstractClass):
        # TODO (mristin, 2024-11-04): implement
        pass
    else:
        assert_never(cls)

    for prop in cls.properties:
        prop.type_annotation

        type_anno = intermediate.beneath_optional(prop.type_annotation)

        maybe_primitive_type = intermediate.try_primitive_type(type_anno)

        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
            # TODO: implement
            raise NotImplementedError()
        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.our_type, intermediate.Enumeration):
                # TODO: implement
                raise NotImplementedError()
            elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
                # TODO: implement
                raise NotImplementedError()
            elif isinstance(
                    type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass)
            ):
                # TODO: implement
                raise NotImplementedError()
            else:
                assert_never(type_anno.our_type)
        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert (
                    isinstance(type_anno.items, intermediate.OurTypeAnnotation)
                    and isinstance(
                type_anno.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass)
            )
            ), (
                f"NOTE (ErikChampion): We expect only lists of classes "
                f"at the moment, but you specified {type_anno}. "
                f"Please contact the developers if you need this feature."
            )

            # TODO: implement
            raise NotImplementedError()
        else:
            assert_never(type_anno)


@ensure(lambda result: not (result[1] is not None) or (len(result[1]) >= 1))
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate(
        symbol_table: intermediate.SymbolTable,
        spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate tne node set according to the symbol table."""
    base_nodeset_key = specific_implementations.ImplementationKey(
        "base_nodeset.xml"
    )

    base_nodeset_text = spec_impls.get(base_nodeset_key, None)
    if base_nodeset_text is None:
        return None, [
            Error(
                None,
                f"The implementation snippet for the base OPC UA nodeset "
                f"is missing: {base_nodeset_key}",
            )
        ]

    try:
        root = ET.fromstring(base_nodeset_text)
    except Exception as err:
        return None, [
            Error(
                None,
                f"Failed to parse the base nodeset XML out of "
                f"the snippet {base_nodeset_key}: {err}",
            )
        ]

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

    for cls in symbol_table.concrete_classes:
        root.extend(
            _generate_definition(
            cls=cls,
                                         our_type_to_identifier=our_type_to_identifier,
            identifier_machine=identifier_machine)
        )

    text = ET.tostring(root, encoding="unicode", method="xml")

    # NOTE (mristin):
    # This approach is slow, but effective. As long as the meta-model is not too big,
    # this should work.
    # noinspection PyUnresolvedReferences
    pretty_text = xml.dom.minidom.parseString(text).toprettyxml(indent="  ")

    return text, None


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
