package org.telegram.prelest.network;

import android.os.Handler;
import android.os.Looper;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.Call;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

/**
 * HTTP и WebSocket клиент Prelestgram.
 * Заменяет tgnet / MTProto — все запросы идут к нашему REST-бэкенду.
 */
public class PrelestApiClient {

    /** Базовый URL API-сервера. Переопределить перед сборкой или брать из BuildConfig. */
    private static final String BASE_URL = "https://api.prelestgram.app";

    /** Тип тела JSON-запросов. */
    private static final MediaType JSON = MediaType.get("application/json; charset=utf-8");

    /** Синглтон: один клиент на всё приложение. */
    private static volatile PrelestApiClient sInstance;

    private final OkHttpClient httpClient;
    /** Хендлер главного потока для доставки колбэков на UI. */
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    // ─── Интерфейс колбэков ───────────────────────────────────────────────

    /**
     * Общий колбэк для REST-вызовов.
     * Все методы вызываются в главном (UI) потоке.
     */
    public interface Callback {
        /** Успешный ответ; data — разобранный JSON-объект. */
        void onSuccess(@NonNull JSONObject data);
        /** Ошибка сети или сервера. */
        void onError(@NonNull String message);
    }

    // ─── Конструктор и синглтон ───────────────────────────────────────────

    private PrelestApiClient() {
        httpClient = new OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .writeTimeout(15, TimeUnit.SECONDS)
                .build();
    }

    /** Получить единственный экземпляр клиента. */
    @NonNull
    public static PrelestApiClient getInstance() {
        if (sInstance == null) {
            synchronized (PrelestApiClient.class) {
                if (sInstance == null) {
                    sInstance = new PrelestApiClient();
                }
            }
        }
        return sInstance;
    }

    // ─── Авторизация ──────────────────────────────────────────────────────

    /**
     * Запросить код авторизации для номера телефона.
     * Сервер отправит код через Telegram-бота.
     *
     * @param phone    номер в формате +7 999 123-45-67
     * @param callback результат запроса
     */
    public void requestCode(@NonNull String phone, @NonNull Callback callback) {
        JSONObject body = new JSONObject();
        try {
            body.put("phone", phone);
        } catch (JSONException e) {
            deliverError(callback, "Ошибка формирования запроса: " + e.getMessage());
            return;
        }
        post("/auth/request-code", null, body, callback);
    }

    /**
     * Проверить код авторизации.
     * При успехе data содержит поля "token" и "user_id".
     *
     * @param phone    номер телефона
     * @param code     6-значный код
     * @param callback результат; при успехе data.getString("token") — JWT
     */
    public void verifyCode(
            @NonNull String phone,
            @NonNull String code,
            @NonNull Callback callback
    ) {
        JSONObject body = new JSONObject();
        try {
            body.put("phone", phone);
            body.put("code", code);
        } catch (JSONException e) {
            deliverError(callback, "Ошибка формирования запроса: " + e.getMessage());
            return;
        }
        post("/auth/verify-code", null, body, callback);
    }

    // ─── Сообщения ────────────────────────────────────────────────────────

    /**
     * Получить список чатов текущего пользователя.
     *
     * @param token    JWT-токен
     * @param callback результат; data.getJSONArray("chats")
     */
    public void getChats(@NonNull String token, @NonNull Callback callback) {
        get("/chats", token, callback);
    }

    /**
     * Получить историю сообщений чата.
     *
     * @param token    JWT-токен
     * @param chatId   идентификатор чата
     * @param callback результат; data.getJSONArray("messages")
     */
    public void getMessages(
            @NonNull String token,
            long chatId,
            @NonNull Callback callback
    ) {
        get("/chats/" + chatId + "/messages", token, callback);
    }

    /**
     * Отправить текстовое сообщение.
     *
     * @param token    JWT-токен
     * @param chatId   идентификатор чата
     * @param text     текст сообщения
     * @param callback результат; data содержит "id" нового сообщения
     */
    public void sendMessage(
            @NonNull String token,
            long chatId,
            @NonNull String text,
            @NonNull Callback callback
    ) {
        JSONObject body = new JSONObject();
        try {
            body.put("chat_id", chatId);
            body.put("content", text);
        } catch (JSONException e) {
            deliverError(callback, "Ошибка формирования запроса: " + e.getMessage());
            return;
        }
        post("/chats/" + chatId + "/messages", token, body, callback);
    }

    // ─── WebSocket ────────────────────────────────────────────────────────

    /**
     * Открыть WebSocket-канал реального времени.
     * Первым сообщением клиент отправляет {"token": "<jwt>"}.
     *
     * @param token    JWT-токен
     * @param userId   идентификатор пользователя
     * @param listener слушатель событий WebSocket
     * @return объект WebSocket (сохранить для закрытия соединения)
     */
    @NonNull
    public WebSocket connectWebSocket(
            @NonNull String token,
            long userId,
            @NonNull WebSocketListener listener
    ) {
        String wsUrl = BASE_URL
                .replace("https://", "wss://")
                .replace("http://", "ws://")
                + "/ws/" + userId;

        Request request = new Request.Builder()
                .url(wsUrl)
                .build();

        WebSocket ws = httpClient.newWebSocket(request, listener);

        // Аутентификация: первое сообщение — JSON с токеном
        JSONObject authMsg = new JSONObject();
        try {
            authMsg.put("token", token);
            ws.send(authMsg.toString());
        } catch (JSONException ignored) {
        }

        return ws;
    }

    // ─── Внутренние вспомогательные методы ───────────────────────────────

    /** Выполнить GET-запрос с опциональным Bearer-токеном. */
    private void get(
            @NonNull String path,
            @Nullable String token,
            @NonNull Callback callback
    ) {
        Request.Builder builder = new Request.Builder().url(BASE_URL + path).get();
        if (token != null) {
            builder.header("Authorization", "Bearer " + token);
        }
        execute(builder.build(), callback);
    }

    /** Выполнить POST-запрос с JSON-телом и опциональным Bearer-токеном. */
    private void post(
            @NonNull String path,
            @Nullable String token,
            @NonNull JSONObject body,
            @NonNull Callback callback
    ) {
        RequestBody reqBody = RequestBody.create(body.toString(), JSON);
        Request.Builder builder = new Request.Builder()
                .url(BASE_URL + path)
                .post(reqBody);
        if (token != null) {
            builder.header("Authorization", "Bearer " + token);
        }
        execute(builder.build(), callback);
    }

    /** Асинхронно выполнить запрос и разобрать JSON-ответ. */
    private void execute(@NonNull Request request, @NonNull Callback callback) {
        httpClient.newCall(request).enqueue(new okhttp3.Callback() {
            @Override
            public void onFailure(@NonNull Call call, @NonNull IOException e) {
                deliverError(callback, "Ошибка сети: " + e.getMessage());
            }

            @Override
            public void onResponse(@NonNull Call call, @NonNull Response response) {
                try (response) {
                    String rawBody = response.body() != null ? response.body().string() : "{}";
                    if (!response.isSuccessful()) {
                        // Попытаться извлечь сообщение об ошибке из JSON
                        String detail = rawBody;
                        try {
                            JSONObject errJson = new JSONObject(rawBody);
                            detail = errJson.optString("detail", rawBody);
                        } catch (JSONException ignored) {
                        }
                        deliverError(callback, "Ошибка сервера " + response.code() + ": " + detail);
                        return;
                    }
                    JSONObject json = new JSONObject(rawBody);
                    deliverSuccess(callback, json);
                } catch (IOException | JSONException e) {
                    deliverError(callback, "Ошибка разбора ответа: " + e.getMessage());
                }
            }
        });
    }

    /** Доставить успешный результат в UI-поток. */
    private void deliverSuccess(@NonNull Callback callback, @NonNull JSONObject data) {
        mainHandler.post(() -> callback.onSuccess(data));
    }

    /** Доставить сообщение об ошибке в UI-поток. */
    private void deliverError(@NonNull Callback callback, @NonNull String message) {
        mainHandler.post(() -> callback.onError(message));
    }
}
