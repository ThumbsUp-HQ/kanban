# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""LDAPv3 ASN.1/BER protocol framing and codecs using pyasn1 (RFC 4511, KB-P2-07)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, cast

from pyasn1.codec.ber import decoder, encoder
from pyasn1.type import namedtype, tag, univ

from kanban.auth.ldap.escape import (
    FilterAnd,
    FilterLeaf,
    FilterNode,
    FilterNot,
    FilterOr,
    parse_filter,
)

if TYPE_CHECKING:
    import asyncio

__all__ = [
    "APPLICATION_TAG_BIND_REQUEST",
    "APPLICATION_TAG_BIND_RESPONSE",
    "APPLICATION_TAG_EXTENDED_REQUEST",
    "APPLICATION_TAG_EXTENDED_RESPONSE",
    "APPLICATION_TAG_SEARCH_REQUEST",
    "APPLICATION_TAG_SEARCH_RES_DONE",
    "APPLICATION_TAG_SEARCH_RES_ENTRY",
    "APPLICATION_TAG_SEARCH_RES_REF",
    "APPLICATION_TAG_UNBIND_REQUEST",
    "MAX_BER_MESSAGE_SIZE",
    "RESULT_CODE_INVALID_CREDENTIALS",
    "RESULT_CODE_OPERATIONS_ERROR",
    "RESULT_CODE_PROTOCOL_ERROR",
    "RESULT_CODE_SUCCESS",
    "RESULT_CODE_UNAVAILABLE",
    "STARTTLS_OID",
    "BindRequest",
    "BindResponse",
    "ExtendedRequest",
    "ExtendedResponse",
    "LDAPMessage",
    "LdapProtocolError",
    "PartialAttribute",
    "PartialAttributeList",
    "ProtocolOp",
    "SearchRequest",
    "SearchResultDone",
    "SearchResultEntry",
    "SimpleBind",
    "UnbindRequest",
    "build_bind_request",
    "build_search_request",
    "build_starttls_request",
    "build_unbind_request",
    "decode_ldap_message",
    "encode_filter_ast",
    "read_ber_packet",
]

MAX_BER_MESSAGE_SIZE: Final[int] = 262144  # 256 KiB
STARTTLS_OID: Final[str] = "1.3.6.1.4.1.1466.20037"

# LDAP Result Codes (RFC 4511 Section 4.1.9)
RESULT_CODE_SUCCESS: Final[int] = 0
RESULT_CODE_OPERATIONS_ERROR: Final[int] = 1
RESULT_CODE_PROTOCOL_ERROR: Final[int] = 2
RESULT_CODE_INVALID_CREDENTIALS: Final[int] = 49
RESULT_CODE_UNAVAILABLE: Final[int] = 52

# Application Tags
APPLICATION_TAG_BIND_REQUEST: Final[int] = 0
APPLICATION_TAG_BIND_RESPONSE: Final[int] = 1
APPLICATION_TAG_UNBIND_REQUEST: Final[int] = 2
APPLICATION_TAG_SEARCH_REQUEST: Final[int] = 3
APPLICATION_TAG_SEARCH_RES_ENTRY: Final[int] = 4
APPLICATION_TAG_SEARCH_RES_DONE: Final[int] = 5
APPLICATION_TAG_SEARCH_RES_REF: Final[int] = 19
APPLICATION_TAG_EXTENDED_REQUEST: Final[int] = 23
APPLICATION_TAG_EXTENDED_RESPONSE: Final[int] = 24

# Scope and Deref aliases constants
SCOPE_BASE_OBJECT: Final[int] = 0
SCOPE_SINGLE_LEVEL: Final[int] = 1
SCOPE_WHOLE_SUBTREE: Final[int] = 2
DEREF_NEVER: Final[int] = 0

# BER Protocol Tags
TAG_BER_SEQUENCE: Final[int] = 0x30
TAG_BER_OCTET_STRING: Final[int] = 0x04
TAG_FILTER_AND: Final[int] = 0xA0
TAG_FILTER_OR: Final[int] = 0xA1
TAG_FILTER_NOT: Final[int] = 0xA2
TAG_FILTER_EQUALITY: Final[int] = 0xA3
TAG_FILTER_GREATER_OR_EQUAL: Final[int] = 0xA5
TAG_FILTER_LESS_OR_EQUAL: Final[int] = 0xA6
TAG_FILTER_PRESENT: Final[int] = 0x87
TAG_FILTER_APPROX: Final[int] = 0xA8
BER_SHORT_LEN_MAX: Final[int] = 0x80
MAX_LEN_OCTETS: Final[int] = 4


class LdapProtocolError(Exception):
    """Raised when an LDAP wire protocol error or message boundary violation occurs."""


class SimpleBind(univ.OctetString):
    """Simple password authentication choice [0]."""

    tagSet = univ.OctetString.tagSet.tagImplicitly(  # noqa: N815
        tag.Tag(tag.tagClassContext, tag.tagFormatSimple, 0)
    )


class BindRequest(univ.Sequence):
    """LDAP BindRequest [APPLICATION 0] (RFC 4511 Section 4.2)."""

    tagSet = univ.Sequence.tagSet.tagImplicitly(  # noqa: N815
        tag.Tag(tag.tagClassApplication, tag.tagFormatConstructed, APPLICATION_TAG_BIND_REQUEST)
    )
    componentType = namedtype.NamedTypes(  # noqa: N815
        namedtype.NamedType("version", univ.Integer()),
        namedtype.NamedType("name", univ.OctetString()),
        namedtype.NamedType("authentication", SimpleBind()),
    )


class BindResponse(univ.Sequence):
    """LDAP BindResponse [APPLICATION 1] (RFC 4511 Section 4.2.3)."""

    tagSet = univ.Sequence.tagSet.tagImplicitly(  # noqa: N815
        tag.Tag(tag.tagClassApplication, tag.tagFormatConstructed, APPLICATION_TAG_BIND_RESPONSE)
    )
    componentType = namedtype.NamedTypes(  # noqa: N815
        namedtype.NamedType("resultCode", univ.Enumerated()),
        namedtype.NamedType("matchedDN", univ.OctetString()),
        namedtype.NamedType("diagnosticMessage", univ.OctetString()),
        namedtype.OptionalNamedType(
            "referral",
            univ.SequenceOf().subtype(
                implicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatConstructed, 3)
            ),
        ),
    )


class UnbindRequest(univ.Null):
    """LDAP UnbindRequest [APPLICATION 2] (RFC 4511 Section 4.3)."""

    tagSet = univ.Null.tagSet.tagImplicitly(  # noqa: N815
        tag.Tag(tag.tagClassApplication, tag.tagFormatSimple, APPLICATION_TAG_UNBIND_REQUEST)
    )


class ExtendedRequest(univ.Sequence):
    """LDAP ExtendedRequest [APPLICATION 23] (RFC 4511 Section 4.12)."""

    tagSet = univ.Sequence.tagSet.tagImplicitly(  # noqa: N815
        tag.Tag(tag.tagClassApplication, tag.tagFormatConstructed, APPLICATION_TAG_EXTENDED_REQUEST)
    )
    componentType = namedtype.NamedTypes(  # noqa: N815
        namedtype.NamedType(
            "requestName",
            univ.OctetString().subtype(
                implicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatSimple, 0)
            ),
        ),
        namedtype.OptionalNamedType(
            "requestValue",
            univ.OctetString().subtype(
                implicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatSimple, 1)
            ),
        ),
    )


class ExtendedResponse(univ.Sequence):
    """LDAP ExtendedResponse [APPLICATION 24] (RFC 4511 Section 4.12)."""

    tagSet = univ.Sequence.tagSet.tagImplicitly(  # noqa: N815
        tag.Tag(
            tag.tagClassApplication, tag.tagFormatConstructed, APPLICATION_TAG_EXTENDED_RESPONSE
        )
    )
    componentType = namedtype.NamedTypes(  # noqa: N815
        namedtype.NamedType("resultCode", univ.Enumerated()),
        namedtype.NamedType("matchedDN", univ.OctetString()),
        namedtype.NamedType("diagnosticMessage", univ.OctetString()),
        namedtype.OptionalNamedType(
            "referral",
            univ.SequenceOf().subtype(
                implicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatConstructed, 3)
            ),
        ),
        namedtype.OptionalNamedType(
            "responseName",
            univ.OctetString().subtype(
                implicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatSimple, 10)
            ),
        ),
        namedtype.OptionalNamedType(
            "responseValue",
            univ.OctetString().subtype(
                implicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatSimple, 11)
            ),
        ),
    )


class AttributeSelection(univ.SequenceOf):
    """AttributeSelection sequence of attribute description strings."""

    componentType = univ.OctetString()  # noqa: N815


class SearchRequest(univ.Sequence):
    """LDAP SearchRequest [APPLICATION 3] (RFC 4511 Section 4.5.1)."""

    tagSet = univ.Sequence.tagSet.tagImplicitly(  # noqa: N815
        tag.Tag(tag.tagClassApplication, tag.tagFormatConstructed, APPLICATION_TAG_SEARCH_REQUEST)
    )
    componentType = namedtype.NamedTypes(  # noqa: N815
        namedtype.NamedType("baseObject", univ.OctetString()),
        namedtype.NamedType("scope", univ.Enumerated()),
        namedtype.NamedType("derefAliases", univ.Enumerated()),
        namedtype.NamedType("sizeLimit", univ.Integer()),
        namedtype.NamedType("timeLimit", univ.Integer()),
        namedtype.NamedType("typesOnly", univ.Boolean()),
        namedtype.NamedType("filter", univ.Any()),
        namedtype.NamedType("attributes", AttributeSelection()),
    )


class AttributeValue(univ.OctetString):
    """Raw attribute value octets."""


class AttributeValues(univ.SetOf):
    """Set of attribute values."""

    componentType = AttributeValue()  # noqa: N815


class PartialAttribute(univ.Sequence):
    """Attribute description and set of values."""

    componentType = namedtype.NamedTypes(  # noqa: N815
        namedtype.NamedType("type", univ.OctetString()),
        namedtype.NamedType("vals", AttributeValues()),
    )


class PartialAttributeList(univ.SequenceOf):
    """Sequence of partial attributes."""

    componentType = PartialAttribute()  # noqa: N815


class SearchResultEntry(univ.Sequence):
    """LDAP SearchResultEntry [APPLICATION 4] (RFC 4511 Section 4.5.2)."""

    tagSet = univ.Sequence.tagSet.tagImplicitly(  # noqa: N815
        tag.Tag(tag.tagClassApplication, tag.tagFormatConstructed, APPLICATION_TAG_SEARCH_RES_ENTRY)
    )
    componentType = namedtype.NamedTypes(  # noqa: N815
        namedtype.NamedType("objectName", univ.OctetString()),
        namedtype.NamedType("attributes", PartialAttributeList()),
    )


class SearchResultDone(univ.Sequence):
    """LDAP SearchResultDone [APPLICATION 5] (RFC 4511 Section 4.5.3)."""

    tagSet = univ.Sequence.tagSet.tagImplicitly(  # noqa: N815
        tag.Tag(tag.tagClassApplication, tag.tagFormatConstructed, APPLICATION_TAG_SEARCH_RES_DONE)
    )
    componentType = namedtype.NamedTypes(  # noqa: N815
        namedtype.NamedType("resultCode", univ.Enumerated()),
        namedtype.NamedType("matchedDN", univ.OctetString()),
        namedtype.NamedType("diagnosticMessage", univ.OctetString()),
        namedtype.OptionalNamedType(
            "referral",
            univ.SequenceOf().subtype(
                implicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatConstructed, 3)
            ),
        ),
    )


class ProtocolOp(univ.Choice):
    """Choice of protocol operations inside LDAPMessage."""

    componentType = namedtype.NamedTypes(  # noqa: N815
        namedtype.NamedType("bindRequest", BindRequest()),
        namedtype.NamedType("bindResponse", BindResponse()),
        namedtype.NamedType("unbindRequest", UnbindRequest()),
        namedtype.NamedType("searchRequest", SearchRequest()),
        namedtype.NamedType("searchResEntry", SearchResultEntry()),
        namedtype.NamedType("searchResDone", SearchResultDone()),
        namedtype.NamedType("extendedReq", ExtendedRequest()),
        namedtype.NamedType("extendedResp", ExtendedResponse()),
    )


class LDAPMessage(univ.Sequence):
    """LDAPMessage envelope (RFC 4511 Section 4.1.1)."""

    componentType = namedtype.NamedTypes(  # noqa: N815
        namedtype.NamedType("messageID", univ.Integer()),
        namedtype.NamedType("protocolOp", ProtocolOp()),
    )


def _encode_ber_length(length: int) -> bytes:
    """Encode length into definite BER octets."""
    if length < BER_SHORT_LEN_MAX:
        return bytes([length])
    octets: list[int] = []
    val = length
    while val > 0:
        octets.append(val & 0xFF)
        val >>= 8
    octets.reverse()
    return bytes([BER_SHORT_LEN_MAX | len(octets)]) + bytes(octets)


def _encode_octet_string(val: bytes) -> bytes:
    """Encode OCTET STRING (tag 0x04)."""
    return bytes([TAG_BER_OCTET_STRING]) + _encode_ber_length(len(val)) + val


def _unescape_filter_assertion(escaped_val: str) -> bytes:
    r"""Convert RFC 4515 escaped assertion string (e.g. \2a, \00) back to raw bytes."""
    out = bytearray()
    i = 0
    n = len(escaped_val)
    while i < n:
        if (
            escaped_val[i] == "\\"
            and i + 2 < n
            and all(c in "0123456789abcdefABCDEF" for c in escaped_val[i + 1 : i + 3])
        ):
            out.append(int(escaped_val[i + 1 : i + 3], 16))
            i += 3
        else:
            out.extend(escaped_val[i].encode("utf-8"))
            i += 1
    return bytes(out)


def _encode_leaf(node: FilterLeaf) -> bytes:
    """Encode a leaf filter into BER bytes."""
    attr_bytes = node.attr.encode("utf-8")
    if node.op == "=*":
        return bytes([TAG_FILTER_PRESENT]) + _encode_ber_length(len(attr_bytes)) + attr_bytes
    val_bytes = _unescape_filter_assertion(node.val)
    inner = _encode_octet_string(attr_bytes) + _encode_octet_string(val_bytes)
    tag_map = {
        "=": TAG_FILTER_EQUALITY,
        ">=": TAG_FILTER_GREATER_OR_EQUAL,
        "<=": TAG_FILTER_LESS_OR_EQUAL,
        "~=": TAG_FILTER_APPROX,
    }
    ber_tag = tag_map.get(node.op)
    if ber_tag is not None:
        return bytes([ber_tag]) + _encode_ber_length(len(inner)) + inner
    msg = f"Unsupported leaf operator: {node.op}"
    raise LdapProtocolError(msg)


def encode_filter_ast(node: FilterNode) -> bytes:
    """Encode a filter AST node into canonical BER bytes."""
    if isinstance(node, FilterLeaf):
        return _encode_leaf(node)

    if isinstance(node, FilterAnd):
        content = b"".join(encode_filter_ast(c) for c in node.children)
        return bytes([TAG_FILTER_AND]) + _encode_ber_length(len(content)) + content

    if isinstance(node, FilterOr):
        content = b"".join(encode_filter_ast(c) for c in node.children)
        return bytes([TAG_FILTER_OR]) + _encode_ber_length(len(content)) + content

    if isinstance(node, FilterNot):
        content = encode_filter_ast(node.child)
        return bytes([TAG_FILTER_NOT]) + _encode_ber_length(len(content)) + content

    msg = f"Unsupported filter node type: {type(node)}"
    raise LdapProtocolError(msg)


def build_starttls_request(message_id: int = 1) -> bytes:
    """Construct ExtendedRequest for StartTLS OID 1.3.6.1.4.1.1466.20037."""
    req = ExtendedRequest()
    req["requestName"] = STARTTLS_OID

    op = ProtocolOp()
    op["extendedReq"] = req

    msg = LDAPMessage()
    msg["messageID"] = message_id
    msg["protocolOp"] = op

    return cast("bytes", encoder.encode(msg))


def build_bind_request(message_id: int, bind_dn: str, password_bytes: bytes) -> bytes:
    """Construct simple BindRequest."""
    req = BindRequest()
    req["version"] = 3
    req["name"] = bind_dn
    req["authentication"] = SimpleBind(password_bytes)

    op = ProtocolOp()
    op["bindRequest"] = req

    msg = LDAPMessage()
    msg["messageID"] = message_id
    msg["protocolOp"] = op

    return cast("bytes", encoder.encode(msg))


def build_search_request(  # noqa: PLR0913, PLR0917
    message_id: int,
    base_dn: str,
    filter_node_or_str: FilterNode | str,
    attributes: list[str],
    size_limit: int = 2,
    time_limit: int = 5,
) -> bytes:
    """Construct SearchRequest with wholeSubtree scope and neverDerefAliases."""
    node = (
        parse_filter(filter_node_or_str)
        if isinstance(filter_node_or_str, str)
        else filter_node_or_str
    )
    filter_bytes = encode_filter_ast(node)

    attr_sel = AttributeSelection()
    for idx, attr in enumerate(attributes):
        attr_sel.setComponentByPosition(idx, univ.OctetString(attr))

    req = SearchRequest()
    req["baseObject"] = base_dn
    req["scope"] = SCOPE_WHOLE_SUBTREE
    req["derefAliases"] = DEREF_NEVER
    req["sizeLimit"] = size_limit
    req["timeLimit"] = time_limit
    req["typesOnly"] = False
    req["filter"] = univ.Any(filter_bytes)
    req["attributes"] = attr_sel

    op = ProtocolOp()
    op["searchRequest"] = req

    msg = LDAPMessage()
    msg["messageID"] = message_id
    msg["protocolOp"] = op

    return cast("bytes", encoder.encode(msg))


def build_unbind_request(message_id: int = 2) -> bytes:
    """Construct UnbindRequest."""
    op = ProtocolOp()
    op["unbindRequest"] = UnbindRequest("")

    msg = LDAPMessage()
    msg["messageID"] = message_id
    msg["protocolOp"] = op

    return cast("bytes", encoder.encode(msg))


def decode_ldap_message(raw_bytes: bytes) -> tuple[int, str, Any]:
    """Decode raw LDAPMessage BER bytes returning (message_id, op_name, op_component)."""
    if len(raw_bytes) > MAX_BER_MESSAGE_SIZE:
        msg = (
            f"MESSAGE_TOO_LARGE: message size {len(raw_bytes)} "
            f"exceeds maximum {MAX_BER_MESSAGE_SIZE}"
        )
        raise LdapProtocolError(msg)

    try:
        decoded, _ = decoder.decode(raw_bytes, asn1Spec=LDAPMessage())
    except Exception as exc:
        msg = f"BER decode failed: {exc}"
        raise LdapProtocolError(msg) from exc

    msg_id = int(decoded["messageID"])
    op = decoded["protocolOp"]
    op_name = op.getName()
    op_val = op.getComponent()
    return msg_id, op_name, op_val


async def read_ber_packet(
    reader: asyncio.StreamReader,
    max_bytes: int = MAX_BER_MESSAGE_SIZE,
) -> bytes:
    """Read a single framing-complete BER SEQUENCE packet from an asyncio stream.

    Enforces that the packet length does not exceed max_bytes prior to reading the payload.
    """
    tag_byte = await reader.readexactly(1)
    if tag_byte[0] != TAG_BER_SEQUENCE:
        msg = f"Protocol error: expected SEQUENCE tag 0x30, got 0x{tag_byte[0]:02x}"
        raise LdapProtocolError(msg)

    first_len_byte = (await reader.readexactly(1))[0]
    if first_len_byte < BER_SHORT_LEN_MAX:
        length = first_len_byte
        header = tag_byte + bytes([first_len_byte])
    else:
        num_octets = first_len_byte & 0x7F
        if num_octets == 0:
            msg = "Indefinite length encoding is prohibited"
            raise LdapProtocolError(msg)
        if num_octets > MAX_LEN_OCTETS:
            msg = "MESSAGE_TOO_LARGE: length octets exceed 4 bytes"
            raise LdapProtocolError(msg)
        length_octets = await reader.readexactly(num_octets)
        length = int.from_bytes(length_octets, "big")
        header = tag_byte + bytes([first_len_byte]) + length_octets

    total_len = len(header) + length
    if total_len > max_bytes:
        msg = f"MESSAGE_TOO_LARGE: message size {total_len} exceeds maximum {max_bytes}"
        raise LdapProtocolError(msg)

    payload = await reader.readexactly(length)
    return header + payload
