local protocol = Proto("tp1ft", "File Transfer Protocol")

local HEADER_SIZE = 9
local DEFAULT_UDP_PORT = 9000

local f_seq_num = ProtoField.uint16("tp1ft.seq", "Sequence Number", base.DEC)
local f_ack_num = ProtoField.uint16("tp1ft.ack", "Acknowledgment Number", base.DEC)
local f_payload_size = ProtoField.uint16("tp1ft.length", "Payload Length", base.DEC)
local f_flags = ProtoField.uint8("tp1ft.flags", "Flags", base.HEX)
local f_flag_data = ProtoField.bool("tp1ft.flags.data", "DATA", 8, nil, 0x01)
local f_flag_ack = ProtoField.bool("tp1ft.flags.ack", "ACK", 8, nil, 0x02)
local f_flag_fin = ProtoField.bool("tp1ft.flags.fin", "FIN", 8, nil, 0x04)
local f_flag_handshake = ProtoField.bool("tp1ft.flags.handshake", "HANDSHAKE", 8, nil, 0x08)
local f_flag_error = ProtoField.bool("tp1ft.flags.error", "ERROR", 8, nil, 0x10)
local f_checksum = ProtoField.uint16("tp1ft.checksum", "Checksum", base.HEX)
local f_payload = ProtoField.bytes("tp1ft.payload", "Payload")
local f_payload_str = ProtoField.string("tp1ft.payload_ascii", "Payload (ASCII)")

protocol.fields = {
    f_seq_num,
    f_ack_num,
    f_payload_size,
    f_flags,
    f_flag_data,
    f_flag_ack,
    f_flag_fin,
    f_flag_handshake,
    f_flag_error,
    f_checksum,
    f_payload,
    f_payload_str,
}

protocol.prefs.udp_port = Pref.uint("UDP port", DEFAULT_UDP_PORT, "UDP port used by TP1 file transfer")

local udp_table = DissectorTable.get("udp.port")
local registered_port = 0

local function parse_tp1_packet(buffer)
    if buffer:len() < HEADER_SIZE then
        return nil
    end

    local payload_size = buffer(4, 2):uint()
    local total_size = HEADER_SIZE + payload_size

    if payload_size > 1400 then
        return nil
    end

    if buffer:len() < total_size then
        return nil
    end

    return {
        payload_size = payload_size,
        total_size = total_size,
    }
end

local function add_payload_fields(subtree, buffer, payload_size)
    if payload_size <= 0 then
        return
    end

    local payload_range = buffer(HEADER_SIZE, payload_size)
    subtree:add(f_payload, payload_range)
    subtree:add(f_payload_str, payload_range:string())
end

function protocol.dissector(buffer, pinfo, tree)
    local parsed = parse_tp1_packet(buffer)
    if not parsed then
        return false
    end

    pinfo.cols.protocol = protocol.name

    local subtree = tree:add(protocol, buffer(0, parsed.total_size), "TP1 File Transfer Protocol")

    subtree:add(f_seq_num, buffer(0, 2))
    subtree:add(f_ack_num, buffer(2, 2))
    subtree:add(f_payload_size, buffer(4, 2))

    local flags_tree = subtree:add(f_flags, buffer(6, 1))
    flags_tree:add(f_flag_data, buffer(6, 1))
    flags_tree:add(f_flag_ack, buffer(6, 1))
    flags_tree:add(f_flag_fin, buffer(6, 1))
    flags_tree:add(f_flag_handshake, buffer(6, 1))
    flags_tree:add(f_flag_error, buffer(6, 1))

    subtree:add(f_checksum, buffer(7, 2))
    add_payload_fields(subtree, buffer, parsed.payload_size)

    return true
end

udp_table:add_for_decode_as(protocol)
protocol:register_heuristic("udp", protocol.dissector)