<template>
  <div id="app">
    <router-view />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from '@/stores/modules/app'

const appStore = useAppStore()

onMounted(() => {
  appStore.initApp()
})
</script>

<style lang="scss">
#app {
  width: 100%;
  height: 100%;
}
</style>

