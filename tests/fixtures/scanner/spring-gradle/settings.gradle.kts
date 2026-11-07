pluginManagement {
    repositories {
        gradlePluginPortal()
    }
    plugins {
        id("org.springframework.boot") version "3.4.1"
        id("io.spring.dependency-management") version "1.1.6"
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "acme-platform"

include("service", ":platform:common")
