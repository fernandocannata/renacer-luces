plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val buildNumber = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()

android {
    namespace = "com.renacer.lightshow"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.renacer.lightshow"
        minSdk = 26
        targetSdk = 34
        versionCode = buildNumber
        versionName = "1.$buildNumber"
    }

    signingConfigs {
        create("renacer") {
            // Firma fija: así cada versión nueva se instala encima de la anterior.
            storeFile = file("renacer.jks")
            storePassword = "renacer-lightshow"
            keyAlias = "renacer"
            keyPassword = "renacer-lightshow"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("renacer")
        }
        debug {
            signingConfig = signingConfigs.getByName("renacer")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
}
