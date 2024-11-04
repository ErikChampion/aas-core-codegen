"""Generate the names for the OPC UA nodeset definitions."""
from aas_core_codegen.common import Identifier
from aas_core_codegen import naming

def data_type_name(identifier: Identifier)->Identifier:
    """
    Generate the data type name in OPC UA corresponding to the given identifier.

    >>> data_type_name(Identifier("Something"))
    'Something'

    >>> data_type_name(Identifier("Something_better"))
    'SomethingBetter'

    >>> data_type_name(Identifier("Some_URL"))
    'SomeUrl'
    """
    return naming.capitalized_camel_case(identifier)
