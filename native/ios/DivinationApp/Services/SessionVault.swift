import Foundation
import Security

struct StoredSession {
    let id: String
    let token: String
}

final class SessionVault {
    private let account = "active-cast-token"
    private let service = "com.yijing.instrument.session"
    private let defaults = UserDefaults.standard

    func save(id: String, token: String) {
        defaults.set(id, forKey: "activeCastSessionId")
        let data = Data(token.utf8)
        let query = baseQuery.merging([
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]) { _, new in new }
        SecItemDelete(baseQuery as CFDictionary)
        SecItemAdd(query as CFDictionary, nil)
    }

    func load() -> StoredSession? {
        guard let id = defaults.string(forKey: "activeCastSessionId") else { return nil }
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var value: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &value) == errSecSuccess,
              let data = value as? Data,
              let token = String(data: data, encoding: .utf8)
        else { return nil }
        return StoredSession(id: id, token: token)
    }

    func clear() {
        defaults.removeObject(forKey: "activeCastSessionId")
        SecItemDelete(baseQuery as CFDictionary)
    }

    private var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }
}
