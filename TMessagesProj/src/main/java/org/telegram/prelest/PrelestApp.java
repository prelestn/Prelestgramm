package org.telegram.prelest;

import android.app.Application;

import org.telegram.prelest.network.PrelestApiClient;

/**
 * Application-класс Prelestgram.
 * Инициализирует API-клиент при старте приложения.
 * Зарегистрировать в AndroidManifest.xml: android:name=".prelest.PrelestApp"
 * (или в том модуле, где задаётся Application).
 */
public class PrelestApp extends Application {

    @Override
    public void onCreate() {
        super.onCreate();
        // Инициализировать синглтон API-клиента при старте
        PrelestApiClient.getInstance();
    }
}
