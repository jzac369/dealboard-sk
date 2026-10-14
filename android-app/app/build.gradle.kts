import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.gms.google-services")
}

// Podpisovanie vydania: údaje o kľúči sú v súbore keystore.properties
// (mimo repozitára, je v .gitignore). Bez neho sa vydanie nepodpíše.
val keystoreProps = Properties().apply {
    val f = rootProject.file("keystore.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

android {
    namespace = "sk.henkukaj.app"
    compileSdk = 36
    defaultConfig {
        applicationId = "sk.henkukaj.app"
        minSdk = 24
        targetSdk = 36
        versionCode = 4
        versionName = "1.4"
    }
    signingConfigs {
        if (keystoreProps.containsKey("storeFile")) {
            create("vydanie") {
                storeFile = rootProject.file(keystoreProps.getProperty("storeFile"))
                storePassword = keystoreProps.getProperty("storePassword")
                keyAlias = keystoreProps.getProperty("keyAlias")
                keyPassword = keystoreProps.getProperty("keyPassword")
            }
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfigs.findByName("vydanie")?.let { signingConfig = it }
        }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.core:core-splashscreen:1.0.1")
    implementation("androidx.biometric:biometric:1.1.0")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    implementation(platform("com.google.firebase:firebase-bom:33.1.2"))
    implementation("com.google.firebase:firebase-messaging-ktx")
}
