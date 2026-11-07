package com.acme.shop.service;

public class Widget {

    private final String id;

    public Widget(String id) {
        this.id = id;
    }

    public String name() {
        return id;
    }
}
