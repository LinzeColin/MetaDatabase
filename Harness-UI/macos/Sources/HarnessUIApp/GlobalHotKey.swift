import Carbon.HIToolbox
import Foundation

final class GlobalHotKey {
    private static let nextSkinSignature: OSType = 0x4855_494E // HUIN
    private static let nextSkinID: UInt32 = 1

    private let action: () -> Void
    private let identifier: EventHotKeyID
    private var hotKeyRef: EventHotKeyRef?
    private var eventHandlerRef: EventHandlerRef?

    static func commandShiftN(action: @escaping () -> Void) throws -> GlobalHotKey {
        try GlobalHotKey(
            keyCode: UInt32(kVK_ANSI_N),
            modifiers: UInt32(cmdKey | shiftKey),
            identifier: EventHotKeyID(signature: nextSkinSignature, id: nextSkinID),
            action: action
        )
    }

    private init(keyCode: UInt32, modifiers: UInt32, identifier: EventHotKeyID, action: @escaping () -> Void) throws {
        self.action = action
        self.identifier = identifier

        var eventType = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )
        let handlerStatus = InstallEventHandler(
            GetApplicationEventTarget(),
            { _, event, context in
                guard let event, let context else { return OSStatus(eventNotHandledErr) }
                var incoming = EventHotKeyID()
                let parameterStatus = GetEventParameter(
                    event,
                    EventParamName(kEventParamDirectObject),
                    EventParamType(typeEventHotKeyID),
                    nil,
                    MemoryLayout<EventHotKeyID>.size,
                    nil,
                    &incoming
                )
                guard parameterStatus == noErr else { return parameterStatus }
                let hotKey = Unmanaged<GlobalHotKey>.fromOpaque(context).takeUnretainedValue()
                guard incoming.signature == hotKey.identifier.signature, incoming.id == hotKey.identifier.id else {
                    return OSStatus(eventNotHandledErr)
                }
                DispatchQueue.main.async { hotKey.action() }
                return noErr
            },
            1,
            &eventType,
            Unmanaged.passUnretained(self).toOpaque(),
            &eventHandlerRef
        )
        guard handlerStatus == noErr else {
            throw NSError(domain: NSOSStatusErrorDomain, code: Int(handlerStatus))
        }

        var registered: EventHotKeyRef?
        let registrationStatus = RegisterEventHotKey(
            keyCode,
            modifiers,
            identifier,
            GetApplicationEventTarget(),
            0,
            &registered
        )
        guard registrationStatus == noErr, let registered else {
            if let eventHandlerRef { RemoveEventHandler(eventHandlerRef) }
            self.eventHandlerRef = nil
            throw NSError(domain: NSOSStatusErrorDomain, code: Int(registrationStatus))
        }
        hotKeyRef = registered
    }

    deinit {
        if let hotKeyRef { UnregisterEventHotKey(hotKeyRef) }
        if let eventHandlerRef { RemoveEventHandler(eventHandlerRef) }
    }
}
