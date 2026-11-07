package com.acme.shop.reports;

import org.springframework.stereotype.Component;

/**
 * A file with a syntax error (AC-5.4): the two imports above still parse, so
 * the facts they carry are recorded and one ``partial_parse_error`` says the
 * rest of the file could not be read.
 */
@Component
public class BrokenReport {

    public void render( {
        return
    }
}
