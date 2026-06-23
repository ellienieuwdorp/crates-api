package io.crates.api.auth

import kotlin.io.encoding.Base64

public class HttpBasicAuth : Authentication {
    public var username: String? = null
    public var password: String? = null

    override fun apply(query: MutableMap<String, List<String>>, headers: MutableMap<String, String>) {
        if (username == null && password == null) return
        val str = (username ?: "") + ":" + (password ?: "")
        val auth = Base64.encode(str.encodeToByteArray())
        headers["Authorization"] = "Basic $auth"
    }
}
