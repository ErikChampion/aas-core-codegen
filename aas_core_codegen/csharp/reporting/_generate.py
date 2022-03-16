"""Generate C# code for reporting errors by including the code directly."""

import io
import textwrap

from icontract import ensure

from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.csharp import (
    common as csharp_common,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(namespace: csharp_common.NamespaceIdentifier) -> str:
    """
    Generate the C# code for reporting errors.

    The ``namespace`` defines the AAS C# namespace.
    """
    blocks = [
        Stripped(
            textwrap.dedent(
                f"""\
                /// <summary>
                /// Capture a path segment of a value in a model.
                /// </summary
                internal abstract class Segment {{
                {I}// Intentionally empty.
                }}"""
            )
        ),
        Stripped(
            textwrap.dedent(
                f"""\
                internal class NameSegment : Segment {{
                {I}internal readonly string Name;
                {I}internal NameSegment(string name)
                {I}{{
                {II}Name = name;
                {I}}}
                }}"""
            )
        ),
        Stripped(
            textwrap.dedent(
                f"""\
                internal class IndexSegment : Segment {{
                {I}internal readonly int Index;
                {I}internal IndexSegment(int index)
                {I}{{
                {II}Index = index;
                {I}}}
                }}"""
            )
        ),
        Stripped(
            textwrap.dedent(
                f"""\
                internal static System.Text.RegularExpressions.Regex VariableNameRe = (
                {I}new  System.Text.RegularExpressions.Regex(
                {II}@"^[a-zA-Z_][a-zA-Z_0-9]*$"));"""
            )
        ),
        # We have to indent a lot so we do not use textwrap.dedent for better
        # readability.
        Stripped(
            f"""\
/// <summary>
/// Generate a JSON Path based on the path segments.
/// </summary>
/// <remarks>
/// See, for example, this page for more information on JSON path:
/// https://support.smartbear.com/alertsite/docs/monitors/api/endpoint/jsonpath.html
/// </remarks>
internal static string GenerateJsonPath(
{I}ICollection<Segment> segments)
{{
{I}var parts = new List<string>(segments.Count);
{I}int i = 0;
{I}foreach(var segment in segments)
{I}{{
{II}string? part = null;
{II}switch (segment)
{II}{{
{III}case NameSegment nameSegment:
{IIII}if (VariableNameRe.IsMatch(nameSegment.Name))
{IIII}{{
{IIIII}part = (i == 0) ? nameSegment.Name : $".{{nameSegment.Name}}";
{IIII}}}
{IIII}else
{IIII}{{
{IIIII}string escaped = nameSegment.Name
{IIIIII}.Replace("\\\\", "\\\\\\\\")
{IIIIII}.Replace("\\"", "\\\\\\"")
{IIIIII}.Replace("\\b", "\\\\b")
{IIIIII}.Replace("\\f", "\\\\f")
{IIIIII}.Replace("\\n", "\\\\n")
{IIIIII}.Replace("\\r", "\\\\r")
{IIIIII}.Replace("\\t", "\\\\t");
{IIIII}part = $"[\\"{{escaped}}\\"]";
{IIII}}}
{IIII}break;
{III}case IndexSegment indexSegment:
{IIII}part = $"[{{indexSegment.Index}}]";
{IIII}break;
{III}default:
{IIII}throw new System.InvalidOperationException(
{IIIII}$"Unexpected segment type: {{segment.GetType()}}");
{II}}}
{II}parts.Add(part);
{I}}}
{I}return string.Join("", parts);
}}"""
        ),
        Stripped(
            textwrap.dedent(
                f"""\
                /// <summary>
                /// Represent an error during the deserialization or the verification.
                /// </summary>
                internal class Error
                {{
                {I}internal LinkedList<Segment> PathSegments = new LinkedList<Segment>();
                {I}internal readonly string Cause;
                {I}internal Error(string cause)
                {I}{{
                {II}Cause = cause;
                {I}}}
                }}"""
            )
        ),
    ]

    writer = io.StringIO()
    writer.write(
        textwrap.dedent(
            f"""\
            namespace {namespace}
            {{
            {I}/// <summary>
            {I}/// Provide reporting for de/serialization and verification.
            {I}/// </summary>
            {I}public static class Reporting
            {I}{{
            """
        )
    )

    for i, deserialize_block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(deserialize_block, II))

    writer.write(f"\n{I}}}  // public static class Reporting")
    writer.write(f"\n}}  // namespace {namespace}")

    # pylint: disable=line-too-long
    blocks = [
        csharp_common.WARNING,
        Stripped("using System.Collections.Generic;  // can't alias"),
        Stripped(f"using Aas = {namespace};"),
        Stripped(writer.getvalue()),
        csharp_common.WARNING,
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        writer.write(block)

    writer.write("\n")

    return writer.getvalue()