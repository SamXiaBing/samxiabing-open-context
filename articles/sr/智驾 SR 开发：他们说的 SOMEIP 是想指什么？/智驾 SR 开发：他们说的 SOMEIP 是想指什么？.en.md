---
title: "Smart Driving SR Development: What Do People Actually Mean by SOME/IP?"
lang: en
date: 2026-06-23
series: sr
no: 
status: published
visibility: public
wechat_url: ""
---

> When developing smart-driving SR (Surround Reality) applications, at first you constantly hear ADAS engineers or Android engineers talking about SOME/IP — things like: "**These signals ride over the SOME/IP protocol**", "That perception type isn't in SOME/IP 3.1; it only arrives in SOME/IP 3.2", "This vehicle model is moving the smart-driving side to SOME/IP 3.3 — align on the protocol differences and assess the impact". But... what on earth is SOME/IP? Haven't the 3D and Android folks already settled on a Protobuf protocol? What does it have to do with me?

SOME/IP (Scalable service-Oriented MiddlewarE over IP) is an automotive Ethernet middleware protocol defined by the AUTOSAR consortium. In the smart-driving SR scenario, it carries all the real-time data from the autonomous driving domain controller to the cockpit display unit.

So it's a protocol — and a protocol, by definition, specifies how data is organized. Think of it as defining the content format of a telegram message. Naturally, I wanted to first understand what that format looks like.

---

# Message structure

## (1) The 16-byte Header

A standard SOME/IP message header is fixed at 16 bytes, always big-endian:


| Offset | Length | Field | Description |
| --- | --- | ---------------------- | --------------------------------------------------------------------- |
| 0 | 4 B | Service ID + Method ID | Together the Message ID; identifies "which method/event of which service" |
| 4 | 4 B | Length | Total number of bytes from just after this field to the end of the message |
| 8 | 4 B | Client ID + Session ID | Request identifier; the server echoes the same IDs in its reply. Used for message pairing. |
| 12 | 1 B | Protocol Version | Protocol version, fixed at 0x01 |
| 13 | 1 B | Interface Version | Major version of the service interface |
| 14 | 1 B | Message Type | 0x00=Request, 0x01=RequestNoReturn, 0x02=Notification, 0x80=Response… |
| 15 | 1 B | Return Code | 0x00=E_OK; the rest are various error codes |


## (2) Payload

The Payload is the bytes immediately following the Header — we can translate it as "**data body**". What's inside is the business data: HD map, perceived objects, planned trajectories, and the like.

The Payload has a defined serialization specification: how application-layer data gets converted into a binary byte stream can be defined. The files that express such interface definitions are written in an ARXML/FIBEX "grammar".

> What goes into ARXML (AUTOSAR XML) and FIBEX (Field Bus Exchange Format) files?
>
> · Service definitions: allocation of Service ID, Method ID, Event ID
>
> · Data type definitions: field layout of struct, union, array, string
>
> · Serialization configuration: byte order, alignment policy, position of the length field
>
> · Version info: Interface Version, for backward compatibility

We can use the relevant toolchain (for example, Vector CANoe) plus the files defined above to auto-generate serialization/deserialization code in C/C++. That spares developers from handling the binary themselves.

> The way I understand it, one way to make a living off the AUTOSAR ecosystem is exactly this: define the protocol, then profit through the toolchain.

Its basic data types include:


| Type | Size | Description |
| --------------- | ---- | ------------------------- |
| boolean | 1 byte | 0x00 = false, 0x01 = true |
| uint8 / sint8 | 1 byte | Unsigned/signed 8-bit integer |
| uint16 / sint16 | 2 bytes | Unsigned/signed 16-bit integer |
| uint32 / sint32 | 4 bytes | Unsigned/signed 32-bit integer |
| uint64 / sint64 | 8 bytes | Unsigned/signed 64-bit integer |
| float32 | 4 bytes | IEEE 754 single-precision float |
| float64 | 8 bytes | IEEE 754 double-precision float |


By default, the Payload is also big-endian, but the interface definition can specify little-endian.

### Alignment, illustrated

What I find most distinctive about this protocol is its **natural alignment** strategy. To improve memory access efficiency (memory is accessed block by block by address; if bytes aren't aligned, you have to stitch them together after the access), every field defined here must start at an address that is an integer multiple of that field type's byte length. If the previous field's end position isn't such a multiple, padding bytes must be inserted.

For example, given a struct like this, I'll explain the alignment through the comments:

```
struct Example {
    uint8_t  a;  // offset 0, length 1; only needs the offset to be a multiple of 1
    uint32_t b;  // must start at offset 4 (uint32_t is a 4-byte type, 4-byte aligned), so offsets 1–3 get 3 padding bytes
    uint16_t c;  // offset 8, length 2; 8 is a multiple of 2, no padding needed
    uint8_t  d;  // offset 10, length 1; 10 is a multiple of 1, no padding needed
    // total size 11 bytes
};

/* Its binary layout
offset 0: a (1B)
offset 1: padding (3B)
offset 4: b (4B)
offset 8: c (2B)
offset 10: d (1B)
*/
```

### Protobuf?

Must the Payload be in the ARXML-defined serialization format? No — it's "arbitrary binary data", a black box. So can we use Protobuf for serialization? Yes!

When SOME/IP transmits, it only looks at the Header. The Header states the Payload length, and those bytes are passed along as-is — whether they contain Protobuf or the ARXML-defined format doesn't matter.

So why would we switch to Protobuf?

- As noted above, the AUTOSAR toolchain costs money, while Protobuf is open source and free.
- Even setting money aside, the toolchain itself has a learning curve, whereas proto is far more widespread across different business domains.
- It's friendlier to Android/Unity development, since code (C++, Java, C#, etc.) can also be generated directly with a tool (protoc).

---

# Core mechanisms

If it were just the message structure, that would look awfully thin — so what else is in there?

It also defines service-oriented communication: Service Discovery, Remote Procedure Calls (RPC), and Event Notification. This kind of protocol lets multiple in-vehicle ECUs exchange structured data over an IP network in "request-response" or "publish-subscribe" patterns.

> In the traditional CAN bus era, ECU addresses were fixed — everyone knew who sat at which ID. In an IP network, though, an ECU's IP address can change dynamically, and services can come online or go offline. So Service Discovery lets an ECU, on startup, actively broadcast its provider ID and port info + periodically broadcast heartbeats + broadcast an offline notice, so clients don't have to hard-code the service provider's info and logic. I won't belabor the other two features; you can see it's all the service concept.

Its core contribution is a **service-oriented communication contract** on top of the IP transport layer. Clients don't need to know the server's concrete address, only the Service ID; once the server comes online it broadcasts an Offer, and once a client subscribes to an EventGroup it automatically receives pushed data.

And to actually implement these mechanisms and ideas, in practice you still use the AUTOSAR toolchain to generate the code — code that includes SD-protocol registration/discovery/heartbeat handling, RPC request/response serialization, and event notification.

## **Must you use the toolchain?**

Just as you might have used proto instead of ARXML, you might also find yourself in a working environment with no AUTOSAR toolchain configured — no automated code generation. What then?

I think the first question to ask is whether your situation truly requires a service-oriented technical approach.

From the smart-driving domain's perspective, I'd say you might well adapt another open-source implementation, such as vsomeip (the SOME/IP protocol stack open-sourced by Volkswagen, in C++).

From the cockpit's perspective, things may get more complicated. Because **in all likelihood, the cockpit's SOME/IP doesn't run on Android but on the QNX Hypervisor**; QNX then sets up another communication middleware (for example, FDBus) and lets Android receive FDBus messages. In other words, for Android app development, the data has already been picked up by another system's system service, and how it gets forwarded is dictated by that system's service.

But **why design it so that QNX takes the SOME/IP** and Android merely receives what QNX forwards? My understanding of the essential reason: it's widely held that QNX's safety and stability make it the better fit as a security gateway — taking SOME/IP while also handling some of the smart-driving domain's permission control and data filtering. Android, by contrast, is positioned more for application presentation; the system itself is comparatively more open and somewhat less stable. Also, Android developers generally know FDBus better. Hence the choice of this architecture — steadier, but costlier to develop.

---

# Data flow

Now that the communication links have been covered above, let me organize that information here. The data flows of a smart-driving SR application, as far as I've encountered them:

**Path 1:** ADCU sends SOME/IP → Android receives and converts to Protobuf → Unity receives custom binary frames and renders.

**Path 2:** ADCU sends SOME/IP → QNX relays (FDBus) → Android receives

> The **ADCU** is the smart-driving side — the SOME/IP Provider (server), continuously pushing ADAS data onto the in-vehicle Ethernet: fused perception objects, HD map, planned trajectories, feature status, and so on.

From a 3D HMI point of view, you're largely insulated from these links: between Android and 3D, the Payload information is still delivered via Socket UDP or JNI + shared memory. **Being insulated from the link doesn't mean you can be insulated from the protocol**. When a pile of binary numbers comes in, we still have to talk about which protocol governs that data.

Sample Android receive/parse code

```java
// Path A: direct UDP receive — packet reception and Protobuf deserialization
void receiveMessage() {
    while (isRunning) {
        socket.receive(packet);
        byte[] raw = packet.getData();
        // Trimmed-down SOME/IP header: first 4B = msgID (little-endian), next 4B = payload length
        int msgId = (raw[3] & 0xFF) << 24 | (raw[2] & 0xFF) << 16
                  | (raw[1] & 0xFF) << 8  | (raw[0] & 0xFF);
        int len   = (raw[7] & 0xFF) << 24 | (raw[6] & 0xFF) << 16
                  | (raw[5] & 0xFF) << 8  | (raw[4] & 0xFF);
        byte[] payload = Arrays.copyOfRange(raw, 8, len + 8);

        switch (msgId) {
            case 0x8015: // HighDefinitionMap
                AdasData.HdMap hdMap = AdasData.HdMap.parseFrom(payload);
                byte[] binary = encodeHdMapToBinary(hdMap);
                udpSender.send(binary, TYPE_HDMAP);
                break;
            // ... other message types ...
        }
    }
}
// Path B: FDBus callback — Protobuf deserialization
@Override
public void onReceive(Object bus, int notifyId, int len, byte[] payload) {
    switch (notifyId) {
        case 2401: // HDMap
            AdasMsg msg = AdasMsg.parseFrom(payload);
            byte[] binary = encodeHdMapToBinary(msg.getHdMap());
            udpSender.send(binary, TYPE_HDMAP);
            break;
        // ...
    }
}
```

Based on real delivery experience, an example of chaining together the **serialization format conversions** in the data flow might look like this:

![Fig. 1](./图1.png)

---

# Closing thoughts

Back to that oft-heard line from the intro: "That perception type isn't in SOME/IP 3.1; it only arrives in SOME/IP 3.2". The version mentioned here isn't actually the spec of the communication protocol itself — it refers to the serialization/deserialization protocol of the Payload's binary data. So a version bump means the Payload protocol may gain more data structure types, and the application layer needs to be able to parse them.
