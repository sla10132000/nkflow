import { createAuth0 } from "@auth0/auth0-vue";
import { createPinia } from "pinia";
import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./style.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);

// Auth0 設定
app.use(
	createAuth0({
		domain: import.meta.env.VITE_AUTH0_DOMAIN || "",
		clientId: import.meta.env.VITE_AUTH0_CLIENT_ID || "",
		authorizationParams: {
			redirect_uri: import.meta.env.VITE_AUTH0_REDIRECT_URI || window.location.origin,
			...(import.meta.env.VITE_AUTH0_AUDIENCE
				? { audience: import.meta.env.VITE_AUTH0_AUDIENCE }
				: {}),
		},
	}),
);

app.mount("#app");
