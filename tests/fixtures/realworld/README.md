
`fixture_t_halvorsen_fake_eps.pdf` is entirely fictional Halvorsen Instruments,
`HALV.FAKE`. It contains dollars in millions, basic/diluted EPS and weighted
average basic/diluted share counts printed in units. It tests optional retention,
independent scaling and money-only statement reconciliation. Build only the new
fixture with `build_pdf_fixtures.build_fixture_t()`; the producer's main command
also builds it alongside the existing fictional fixtures.
