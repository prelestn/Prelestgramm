package org.telegram.prelest.auth;

import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;

import org.json.JSONException;
import org.json.JSONObject;
import org.telegram.prelest.network.PrelestApiClient;

/**
 * Экран авторизации Prelestgram.
 * Шаг 1: ввод номера телефона → запрос кода.
 * Шаг 2: ввод кода → проверка → сохранение JWT → переход в главный экран.
 */
public class PrelestAuthActivity extends AppCompatActivity {

    /** Ключи SharedPreferences. */
    public static final String PREFS_NAME = "prelestgram_prefs";
    public static final String KEY_JWT_TOKEN = "jwt_token";
    public static final String KEY_USER_ID = "user_id";

    // ─── UI ──────────────────────────────────────────────────────────────

    private LinearLayout layoutPhone;
    private LinearLayout layoutCode;

    private EditText editPhone;
    private EditText editCode;

    private Button btnRequestCode;
    private Button btnVerifyCode;

    private ProgressBar progressBar;

    /** Введённый пользователем номер телефона (сохраняем между шагами). */
    private String enteredPhone = "";

    // ─── Lifecycle ────────────────────────────────────────────────────────

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Если уже авторизованы — пропустить экран
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        if (!TextUtils.isEmpty(prefs.getString(KEY_JWT_TOKEN, ""))) {
            navigateToMain();
            return;
        }

        buildUi();
    }

    // ─── Построение UI программно (без XML-лейаута) ───────────────────────

    private void buildUi() {
        int dp16 = dp(16);
        int dp8 = dp(8);

        // Корневой контейнер
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp16, dp(48), dp16, dp16);
        root.setGravity(Gravity.TOP | Gravity.CENTER_HORIZONTAL);
        setContentView(root);

        // Заголовок
        TextView title = new TextView(this);
        title.setText("Prelestgram");
        title.setTextSize(28f);
        title.setGravity(Gravity.CENTER);
        title.setPadding(0, 0, 0, dp(32));
        root.addView(title);

        progressBar = new ProgressBar(this);
        progressBar.setVisibility(View.GONE);
        LinearLayout.LayoutParams pbParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT
        );
        pbParams.gravity = Gravity.CENTER;
        root.addView(progressBar, pbParams);

        // ── Блок ввода телефона ──
        layoutPhone = new LinearLayout(this);
        layoutPhone.setOrientation(LinearLayout.VERTICAL);
        root.addView(layoutPhone);

        TextView labelPhone = new TextView(this);
        labelPhone.setText("Введите номер телефона");
        labelPhone.setPadding(0, 0, 0, dp8);
        layoutPhone.addView(labelPhone);

        editPhone = new EditText(this);
        editPhone.setHint("+7 999 123-45-67");
        editPhone.setInputType(
                android.text.InputType.TYPE_CLASS_PHONE
        );
        editPhone.setSingleLine(true);
        layoutPhone.addView(editPhone);

        btnRequestCode = new Button(this);
        btnRequestCode.setText("Получить код");
        LinearLayout.LayoutParams btnParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        );
        btnParams.topMargin = dp(12);
        layoutPhone.addView(btnRequestCode, btnParams);
        btnRequestCode.setOnClickListener(v -> onRequestCode());

        // ── Блок ввода кода ──
        layoutCode = new LinearLayout(this);
        layoutCode.setOrientation(LinearLayout.VERTICAL);
        layoutCode.setVisibility(View.GONE);
        root.addView(layoutCode);

        TextView labelCode = new TextView(this);
        labelCode.setText("Введите код из Telegram");
        labelCode.setPadding(0, 0, 0, dp8);
        layoutCode.addView(labelCode);

        editCode = new EditText(this);
        editCode.setHint("123456");
        editCode.setInputType(
                android.text.InputType.TYPE_CLASS_NUMBER
        );
        editCode.setSingleLine(true);
        editCode.setMaxLines(1);
        layoutCode.addView(editCode);

        btnVerifyCode = new Button(this);
        btnVerifyCode.setText("Войти");
        LinearLayout.LayoutParams btnCodeParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        );
        btnCodeParams.topMargin = dp(12);
        layoutCode.addView(btnVerifyCode, btnCodeParams);
        btnVerifyCode.setOnClickListener(v -> onVerifyCode());

        // Кнопка «Назад» (смена номера)
        Button btnBack = new Button(this);
        btnBack.setText("Изменить номер");
        LinearLayout.LayoutParams backParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        );
        backParams.topMargin = dp8;
        layoutCode.addView(btnBack, backParams);
        btnBack.setOnClickListener(v -> showPhasePhone());
    }

    // ─── Логика авторизации ───────────────────────────────────────────────

    /** Шаг 1: запросить код авторизации. */
    private void onRequestCode() {
        String phone = editPhone.getText().toString().trim();
        if (TextUtils.isEmpty(phone)) {
            toast("Введите номер телефона");
            return;
        }
        enteredPhone = phone;
        setLoading(true);

        PrelestApiClient.getInstance().requestCode(phone, new PrelestApiClient.Callback() {
            @Override
            public void onSuccess(@NonNull JSONObject data) {
                setLoading(false);
                showPhaseCode();
            }

            @Override
            public void onError(@NonNull String message) {
                setLoading(false);
                toast("Ошибка: " + message);
            }
        });
    }

    /** Шаг 2: проверить код. */
    private void onVerifyCode() {
        String code = editCode.getText().toString().trim();
        if (code.length() != 6) {
            toast("Код должен быть 6 цифр");
            return;
        }
        setLoading(true);

        PrelestApiClient.getInstance().verifyCode(
                enteredPhone,
                code,
                new PrelestApiClient.Callback() {
                    @Override
                    public void onSuccess(@NonNull JSONObject data) {
                        setLoading(false);
                        try {
                            String token = data.getString("token");
                            long userId = data.getLong("user_id");
                            saveCredentials(token, userId);
                            navigateToMain();
                        } catch (JSONException e) {
                            toast("Ошибка разбора ответа");
                        }
                    }

                    @Override
                    public void onError(@NonNull String message) {
                        setLoading(false);
                        toast("Ошибка: " + message);
                    }
                }
        );
    }

    /** Сохранить JWT и user_id в SharedPreferences. */
    private void saveCredentials(@NonNull String token, long userId) {
        getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                .edit()
                .putString(KEY_JWT_TOKEN, token)
                .putLong(KEY_USER_ID, userId)
                .apply();
    }

    // ─── Навигация между фазами ───────────────────────────────────────────

    private void showPhasePhone() {
        layoutPhone.setVisibility(View.VISIBLE);
        layoutCode.setVisibility(View.GONE);
    }

    private void showPhaseCode() {
        layoutPhone.setVisibility(View.GONE);
        layoutCode.setVisibility(View.VISIBLE);
    }

    /** Перейти в главный экран (LaunchActivity Telegram). */
    private void navigateToMain() {
        // Запускаем стандартный LaunchActivity Telegram
        try {
            Intent intent = new Intent(
                    this,
                    Class.forName("org.telegram.ui.LaunchActivity")
            );
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
            startActivity(intent);
        } catch (ClassNotFoundException e) {
            // Fallback: просто завершить этот экран
            finish();
        }
    }

    // ─── Вспомогательные методы ───────────────────────────────────────────

    private void setLoading(boolean loading) {
        progressBar.setVisibility(loading ? View.VISIBLE : View.GONE);
        btnRequestCode.setEnabled(!loading);
        btnVerifyCode.setEnabled(!loading);
    }

    private void toast(@NonNull String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

    /** Перевести dp в пиксели. */
    private int dp(int value) {
        float density = getResources().getDisplayMetrics().density;
        return Math.round(value * density);
    }
}
