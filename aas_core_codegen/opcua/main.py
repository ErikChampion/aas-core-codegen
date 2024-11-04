"""Generate the OPC UA Schema node set corresponding to the meta-model."""
import collections
import io
from typing import TextIO, Tuple, Optional, List, MutableMapping, Mapping
import xml.etree.ElementTree as ET
import xml.dom.minidom

from icontract import ensure

import aas_core_codegen.opcua
from aas_core_codegen import run, intermediate, specific_implementations
from aas_core_codegen.common import Stripped, Error
import aas_core_codegen.opcua.naming as opcua_naming

assert aas_core_codegen.opcua.__doc__ == __doc__


def _generate_aliases(
        symbol_table: intermediate.SymbolTable,
        class_to_identifier: Mapping[intermediate.Class, int]
) -> ET.Element:
    """Generate the aliases including the primitive values."""
    aliases = ET.Element("Aliases")

    alias_boolean = ET.Element("Alias", {"Alias": "Boolean"})
    alias_boolean.text = "i=1"
    aliases.append(alias_boolean)

    # TODO (mristin, 2024-11-04): add more primitive values

    for cls in symbol_table.classes:
        alias = ET.Element("Alias", {"Alias": opcua_naming.data_type_name(cls.name)})
        alias.text = f"ns=1;i={class_to_identifier[cls]}"

        aliases.append(alias)

    return aliases


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

    class_to_identifier = collections.OrderedDict(
    )  # type: MutableMapping[intermediate.Class, int]
    for i, cls in enumerate(symbol_table.classes):
        class_to_identifier[cls] = 5000 + i

    aliases = _generate_aliases(
        symbol_table=symbol_table,
        class_to_identifier=class_to_identifier
    )

    root.append(aliases)

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
