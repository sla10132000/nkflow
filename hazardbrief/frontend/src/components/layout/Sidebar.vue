<script setup lang="ts">
import { useRouter, useRoute } from "vue-router";

const router = useRouter();
const route = useRoute();

const navItems = [
	{ path: "/dashboard", label: "物件一覧", icon: "🏠" },
	{ path: "/properties/new", label: "物件登録", icon: "+" },
	{ path: "/settings", label: "設定", icon: "⚙" },
];
</script>

<template>
  <aside class="w-56 bg-white border-r border-gray-200 min-h-screen flex flex-col">
    <nav class="flex-1 pt-4">
      <ul class="space-y-1 px-3">
        <li v-for="item in navItems" :key="item.path">
          <RouterLink
            :to="item.path"
            :class="[
              'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
              route.path === item.path
                ? 'bg-blue-50 text-blue-700 font-medium'
                : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
            ]"
          >
            <span class="w-5 text-center">{{ item.icon }}</span>
            {{ item.label }}
          </RouterLink>
        </li>
      </ul>
    </nav>

    <!-- 免責事項 -->
    <div class="p-4 border-t border-gray-100">
      <p class="text-xs text-gray-400 leading-relaxed">
        本サービスのレポートは公的機関のデータを基に作成しています。
        物件の安全性判断は専門家への相談と合わせてご活用ください。
      </p>
    </div>
  </aside>
</template>
