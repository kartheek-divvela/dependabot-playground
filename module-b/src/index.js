const express = require('express');
const { v4: uuid } = require('uuid');
function createApp() { return express(); }
function requestId() { return uuid(); }
module.exports = { createApp, requestId };
