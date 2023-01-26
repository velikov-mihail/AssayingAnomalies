function sendUserResults(signalInfo)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It sends a .zip file to the end user
%------------------------------------------------------------------------------------------
% USAGE:   
% sendUserResults(signalInfo)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -signalInfo - a structure containing information about signal from
%                       the website form
%             -signalInfo.Authors - author(s) name(s)
%             -signalInfo.email - corresponding author email address
%             -signalInfo.PaperTitle - paper title
%             -signalInfo.SignalName - signal name
%             -signalInfo.SignalAcronym - signal acronym
%             -signalInfo.fileLink - link to submitted .csv file
%------------------------------------------------------------------------------------------
% Output:
%        - N/A
%------------------------------------------------------------------------------------------
% Examples:
%
% sendUserResults(signalInfo)
%------------------------------------------------------------------------------------------
% Dependencies:
%       Used by runTestSignal()
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\nNow working on emailing the user the output files. Run started at %s.\n', char(datetime('now')));

% Zip the files
filePath = [pwd, filesep, 'Scratch', filesep, 'Assay', filesep, 'tex', filesep];
addpath(filePath);
zip([filePath, signalInfo.SignalAcronym], {[filePath,signalInfo.SignalAcronym, '*.tex'], ...
                                          [filePath, signalInfo.SignalAcronym, '*.pdf'], ...
                                          ['test_', signalInfo.SignalAcronym, '*.txt'], ...
                                          [filePath, 'newSignalTestBib.bib']});

% Prepare the email connection
mail = char(inputdlg('','Enter your email address:',[1 82],{''}));
password = char(inputdlg('','Enter your password:',[1 82],{''})); 
setpref('Internet','SMTP_Server','smtp.gmail.com');
setpref('Internet','E_mail',mail);
setpref('Internet','SMTP_Username',mail);
setpref('Internet','SMTP_Password',password);
props = java.lang.System.getProperties;
props.setProperty('mail.smtp.auth','true');
props.setProperty('mail.smtp.starttls.enable','true');
props.setProperty('mail.smtp.socketFactory.class', 'javax.net.ssl.SSLSocketFactory');
props.setProperty('mail.smtp.socketFactory.port','465');

% Send the email
recipient = signalInfo.email;
subject = ['Assaying Anomalies protocol results for ', signalInfo.SignalAcronym];
message = ['Dear ', signalInfo.Authors, ',' 10 10, ...
           'Attached to this email please find the results from running the tests ', ...
           'in the Novy-Marx and Velikov (2023) "Assaying Anomalies" protocol for the ', ...
           signalInfo.SignalName,' signal.', 10 10, ...
           'Regards,', 10, ...
           'The Assaying Anomalies Team', 10, ...
           'http://assayinganomalies.com'];
attachments = [filePath, signalInfo.SignalAcronym, '.zip'];
sendmail(recipient, subject, message, attachments);

% Timekeeping
fprintf('Email sent at at %s.\n', char(datetime('now')));
