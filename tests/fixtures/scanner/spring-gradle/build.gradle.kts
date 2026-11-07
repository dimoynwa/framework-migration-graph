// The root project publishes the plugin version ``apply false``: it declares
// the version without using the plugin itself (FR-3 case 3, inherited).
plugins {
    java
    id("org.springframework.boot") version "3.4.1" apply false
}

allprojects {
    group = "com.acme"
    version = "1.0.0"
}
