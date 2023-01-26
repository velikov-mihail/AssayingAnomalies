%% Toolkit usage
% This page contains a tutorial on how to implement various basic asset pricing 
% techniques using the Toolkit. These include univariate sorts, bivariate sorts, 
% Fama-MacBeth regressions, and accounting for transaction costs.

% Let's start by setting the path, assuming we have just opened a new instance 
% of MATLAB:

clear
clc

restoredefaultpath;                                                        % Start with the default path
fileName = matlab.desktop.editor.getActiveFilename;                        % Path to the script 
dirSepIndex = strfind(fileName, filesep);                                  % Index of directory separators
fullPath = fileName(1:dirSepIndex(end));                                   % Path to the package

% Add the relevant folders (with subfolders) to the path
addpath(genpath([fullPath, 'Data']))
addpath(genpath([fullPath, 'Functions']))
cd(fullPath)

% Check if Scratch exists, make it if not
if ~exist([fullPath, 'Scratch'], 'dir')
  mkdir([fullPath, 'Scratch']);
  addpath([fullPath, 'Scratch']);
else 
  addpath([fullPath, 'Scratch']);
end

%% Univariate sorts

% Load some variables
clear
clc

load ret
load me
load dates
load pdates
load ff
load NYSE
load exchcd
load tcosts


% Quintile sort on size, name breaks by default
ind = makeUnivSortInd(-me, 5);                                 
res1 = runUnivSort(ret, ind, dates, me);  

% Tertile Fama-French-style sort, name breaks by default
ind = makeUnivSortInd(-me, [30 70]);                                       
res2 = runUnivSort(ret, ind, dates, me);       

% Decile sort, NYSE breaks
ind = makeUnivSortInd(-me, 10, 'breaksFilter', NYSE);                      
res3 = runUnivSort(ret, ind, dates, me); 

% We don't need to specify the 'Name' component for the first optional 
% argument ('breaksFilter'), so the following would also work
ind = makeUnivSortInd(-me, 10, NYSE);                        
res4 = runUnivSort(ret, ind, dates, me);

% Decile sort, NASDAQ breaks (NASDAQ exchcd is 3, starts in 1973)
ind = makeUnivSortInd(-me, 10, (exchcd==3));                     
res5 = runUnivSort(ret, ind, dates, me);

% Quintile sort, market-capitalization breaks
ind = makeUnivSortInd(-me, 5,'portfolioMassInd', me);
res6 = runUnivSort(ret, ind, dates, me);

% Start with just the required arguments (same as res1 above)
ind = makeUnivSortInd(-me, 5);                                             
res7 = runUnivSort(ret, ind, dates, me);        

% Equal-weighting (we'll just keep using the ind from above)
res8 = runUnivSort(ret, ind, dates, me, 'weighting', 'e');     

% 2-month holding period
res9 = runUnivSort(ret, ind, dates, me, 'holdingPeriod', 2);   

% 6-factor model alphas and loadings
res10 = runUnivSort(ret, ind, dates, me, 'factorModel', 6);     

% User defined factor model. In this example, it is still FF6
res11 = runUnivSort(ret, ind, dates, me, 'factorModel', ff6(:,2:end));  

% Don't print the results
res12 = runUnivSort(ret, ind, dates, me, 'printResults', 0);     

% Don't plot the figure
res13 = runUnivSort(ret, ind, dates, me, 'plotFigure', 0);                 

% Start sample in 196307
res14 = runUnivSort(ret, ind, dates, me, 'timePeriod', 196307);    

% Start sample in 192601 and end in 196306
res15 = runUnivSort(ret, ind, dates, me, 'timePeriod', [192601 196306]); 

% Do not add long/short portfolio
res16 = runUnivSort(ret, ind, dates, me, 'addLongShort', 0);     

% Calculate tcosts, net returns, and turnover usging the tcosts matrix
res17 = runUnivSort(ret, ind, dates, me, 'tcosts', tcosts);           

% Order doesn't matter
res18 = runUnivSort(ret, ind, dates, me, 'factorModel', 4, ...             
                                         'weighting', 'v', ...
                                         'timePeriod', 192512, ...
                                         'holdingPeriod', 2, ...
                                         'plotFigure', 0);                

% Specify all optional inputs
res19 = runUnivSort(ret, ind, dates, me, 'weighting', 'v', ...               
                                         'holdingPeriod', 1, ...
                                         'factorModel', 4, ...
                                         'printResults', 1, ...
                                         'plotFigure', 0, ...
                                         'timePeriod', 192512, ...
                                         'addLongShort', 1, ...
                                         'tcosts', 0); 

% Works without specifying the 'Name' part of the arguments too, although 
% they have to  be in this specific order (as specified in the function)
res20 = runUnivSort(ret, ind, dates, me, 'v', 1, 4, 1, 0, 192512, 1, 0); 

% Works even if you only specify the inputs partially, as long as they are
% in correct order
res21 = runUnivSort(ret, ind, dates, me, 'v', 1, 5, 1, 0);                         

% This causes an error - weighting has to be one of 'V', 'v' (default), 'E', 'e'
[~] = runUnivSort(ret, ind, dates, me, 'text');                         

% This causes an error - weighting has to be one of 'V', 'v' (default), 'E', 'e'
[~] = runUnivSort(ret, ind, dates, me, 'weighting', 'equal');            

% This causes an error - factorModel has to be one of 1, 3, 4, 5, 6 or a user-defined matrix
[~] = runUnivSort(ret, ind, dates, me, 'factorModel', 2);                

% This causes an error - timePeriod has to be YYYYMM or [YYYYMM YYYYMM]
[~] = runUnivSort(ret, ind, dates, me, 'timePeriod', 1963);              


%% Bivariate sorts

% Load some variables
clear
clc

load me
load ff
load bm
load R
load dates
load NYSE
load ret


% 5x5 sort on size and momentum. 
ind = makeBivSortInd(me, 5, R, 5);                                                 
[res1, cond_res1] = runBivSort(ret, ind, 5, 5, dates, me); 

% 2x3 (FF-style tertiles) sort on size and momentum
ind = makeBivSortInd(me, 2, R, [30 70]);                                           
[res2, cond_res2] = runBivSort(ret, ind, 2, 3, dates, me); 

% 5x5 sort on size and momentum. Specify conditional sort 
ind = makeBivSortInd(me, 5, R, 5, 'sortType', 'conditional');  
[res3, cond_res3] = runBivSort(ret, ind, 5, 5, dates, me); 

% 5x5 sort on size and momentum. Specify NYSE breaks
ind = makeBivSortInd(me, 5, R, 5, 'breaksFilterInd', NYSE);      
[res4, cond_res4] = runBivSort(ret, ind, 5, 5, dates, me); 

% 5x5 sort on size and momentum. Specify cap breaks
ind = makeBivSortInd(me, 5, R, 5, 'portfolioMassInd', me);                              
[res5, cond_res5] = runBivSort(ret, ind, 5, 5, dates, me); 

% 5x5 sort on size and momentum. Specify NYSE breaks and conditional sort 
ind = makeBivSortInd(me, 5, R, 5, 'sortType', 'unconditional', ...
                                  'breaksFilterInd', NYSE);  
[res6, cond_res6] = runBivSort(ret, ind, 5, 5, dates, me); 

% 5x5 sort on size and momentum. Specify NYSE breaks and conditional sort 
ind = makeBivSortInd(me, 5, R, 5, 'unconditional', NYSE);                          
[res7, cond_res7] = runBivSort(ret, ind, 5, 5, dates, me); 

%% Replicating Fama and French (1993)

% Load some variables
clear
clc

load ret
load dates
load me
load NYSE
load bm

% Fama-French get rid of negative BE firms
bm(bm<0) = nan;

% Do the double sort
ind = makeBivSortInd(me, 5, bm, 5, 'unconditional', NYSE);
[res8, cond_res8] = runBivSort(ret, ind, 5, 5, dates, me, 'timePeriod', [196306 199112]); 

% Download the 25 portfolios from Ken French's data library
fileURL = 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/25_Portfolios_5x5_CSV.zip';
ff25FileName = unzip(fileURL, 'Scratch');

% Read in the the 25 portfolios
opts = detectImportOptions(char(ff25FileName));
FF25factors = readtable(char(ff25FileName), opts);

% Clean them up
e = find(isnan(FF25factors.Var1), 1, 'first');
FF25factors = FF25factors(1:e-1,:);
[~, ia, ib] = intersect(dates, FF25factors.Var1);
ff25 = nan(length(dates), 25);
ff25(ia,:) = table2array(FF25factors(ib, 2:end))/100;

% Plot a scatter plot with the average returns against ours
s = find(dates==196307);
e = find(dates==199112);
figure;
scatter(mean(res8.pret,1,'omitnan'), mean(ff25(s:e,:), 1, 'omitnan'));
xlabel('Replication');
ylabel('Ken French Data Library');
title('Average Returns to 25 size/btm portfolios');
refline

%% Replicating Ken French's momentum

% Load a few variables
clear
clc

load ret
load me
load dates
load NYSE
load R
load ff

% Start by making the 6 (= 2x3) base portfolios
ind = makeBivSortInd(me, 2, R, [30 70], 'unconditional', NYSE); 
[res, ~] = runBivSort(ret, ind, 2, 3, dates, me, 'weighting', 'v', ...
                                                 'holdingPeriod', 1, ...
                                                 'factorModel', 4, ...
                                                 'printResults',1, ...
                                                 'plotFigure',0); 
% UMD is made from the "corner" portfolios
umdrep = (res.pret(:,3) + res.pret(:,6) - ...
         (res.pret(:,1) + res.pret(:,4)) )/2;      

% Look at their correlations     
fprintf('\n\nLook at the correlation between UMD from Ken French and replicated UMD:\n');
indFin = isfinite(sum([umdrep umd],2));
corrcoef([umdrep(indFin) umd(indFin)]) 

% Look at their average returns
fprintf('\n\nCompare the average return UMD from Ken French and replicated UMD:\n');
prt(nanols(umd(indFin), const(indFin))) 
prt(nanols(umdrep(indFin), const(indFin)))

% Regress the two on each other
fprintf('\n\nRegress the two on each other:\n');
prt(nanols(umd, [const umdrep]))
prt(nanols(umdrep, [const umd]))
% Plot the two series
ibbots([umd umdrep], dates, 'timePeriod', 192801, ...
                            'legendLabels', {'UMD','UMDrep'});



%% Fama-MacBeth regressions

% Load a few variables
clear
clc

load me
load bm
load R
load dates
load ret

% Let's start with a basic example, where we estimate a Fama-MacBeth regression 
% of returns on the log of market capitalization and the momentum signal
runFamaMacBeth(100*ret, [log(me) R], dates);

% High mininimum number of observations
runFamaMacBeth(100*ret, [log(me) R], dates, 'minObs', 1000);

% Use WLS for cross-sectional regressions with market caps as the weights
runFamaMacBeth(100*ret, [log(me) R], dates, 'weightMatrix', me);

% Use Newey-West standard errors 
runFamaMacBeth(100*ret, [log(me) R], dates, 'neweyWestLags', 12);

% Use a different starting point for the sample
runFamaMacBeth(100*ret, [log(me) R], dates, 'timePeriod', 196307);

% Use a different sample
runFamaMacBeth(100*ret, [log(me) R], dates, 'timePeriod', [192807 196306]);

% Trim the independent variables instead of winsorizing them
runFamaMacBeth(100*ret, [log(me) R], dates, 'trimIndicator', 1);

% Winsorize at the five percent level
runFamaMacBeth(100*ret, [log(me) R], dates, 'winsorTrimPctg', 5);

% Suppres the constant
runFamaMacBeth(100*ret, [log(me) R], dates, 'noConst', 1);

% Annually-updated variables (e.g., bm) are automatically filled in
runFamaMacBeth(100*ret, [log(me) log(bm) R], dates); 

% Keep any warnings
runFamaMacBeth(100*ret, [log(me) log(bm) R], dates, 'keepWarnings', 1);

% Include labels when printing the results
runFamaMacBeth(100*ret, [log(me) log(bm) R], dates, 'labels', {'Const','log(me)','log(bm)','Momentum'});

%% Transaction costs

% Load some variables
clear
clc

load gibbs_filled
load ret
load dates
load me
load nyse
load R

% Sort first
ind = makeUnivSortInd(R, 10, NYSE);                   

% Speed it up as the tcost calculation for all 10 ptfs takes a while (this will only calculate it for the short (=1) and long (=10) sides)
ind = 1 * (ind==1) + ...
      2 * (ind==10); 
res = runUnivSort(ret, ind, dates, me, 'timePeriod', [196306 201212], ...
                                        'tcosts', tcosts, ...
                                        'plotFigure', 0, ...
                                        'printResults', 0);

% Print it
fprintf('\n\nGross return (t-stat) on momentum from Novy-Marx and Velikov (RFS, 2016), Table 3: %2.2f%%/mo (%2.2f).\n\n', res.xret(end), res.txret(end));
fprintf('\n\nNet return (t-stat) on momentum from Novy-Marx and Velikov (RFS, 2016), Table 3: %2.2f%%/mo (%2.2f).\n\n', res.netxret(end), res.tnetxret(end));


%% Price vs fundamental momentum

% Load a few variables
clear
clc

load ret
load me
load dates
load nyse
load ff

% Read in the momentum and two PEAD signals from the novyMarxVelikovAnomalies.csv
[anoms, ~] = getAnomalySignals('novyMarxVelikovAnomalies.csv', 'permno', 'dates', ...
                                                'anomalyNames', {'momentum','peadSUE','peadCAR3'});

% Assign the three anomaly signals
mom = anoms(:,:,1);
peadSUE = anoms(:,:,2);
peadCAR3 = anoms(:,:,3);

% Show this using Fama-MacBeth regressions
load bm
load r
load GP
load AT
load FinFirms
gp=GP./AT;

% Table 1, column 1
runFamaMacBeth(100*ret, [R log(me) log(bm) gp ret], dates, 'timePeriod', [197501 201212], ...
                                                           'labels', {'Const','r_{2,12}','ln(ME)','ln(B/M)','GP/A','r_{0,1}'}); 

% Table 1, column 2
runFamaMacBeth(100*ret, [peadSUE peadCAR3 log(me) log(bm) gp ret], dates, 'timePeriod', [197501 201212], ...
                                                                          'labels',{'Const','SUE','CAR3','ln(ME)','ln(B/M)','GP/A','r_{0,1}'}); 

% Table 1, column 3
runFamaMacBeth(100*ret, [R peadSUE peadCAR3 log(me) log(bm) gp ret], dates, 'timePeriod', [197501 201212], ...
                                                                            'labels',{'Const','r_{2,12}','SUE','CAR3','ln(ME)','ln(B/M)','GP/A','r_{0,1}'}); 

% Now let's show it using spanning tests
% Start by making the 6 (= 2x3) base portfolios
ind = makeBivSortInd(me, 2, peadSUE, [30 70], 'unconditional', NYSE); 
[resSUE, ~] = runBivSort(ret, ind, 2, 3, dates, me, 'weighting', 'v', ...
                                                 'holdingPeriod', 1, ...
                                                 'factorModel', 4, ...
                                                 'printResults', 0, ...
                                                 'plotFigure',0); 
% SUE is made from the "corner" portfolios
sue = (resSUE.pret(:,3) + resSUE.pret(:,6) - ...
         (resSUE.pret(:,1) + resSUE.pret(:,4)) )/2;   


% Start by making the 6 (= 2x3) base portfolios
ind = makeBivSortInd(me, 2, peadCAR3, [30 70], 'unconditional', NYSE); 
[resCAR3, ~] = runBivSort(ret, ind, 2, 3, dates, me, 'weighting', 'v', ...
                                                 'holdingPeriod', 1, ...
                                                 'factorModel', 4, ...
                                                 'printResults', 0, ...
                                                 'plotFigure',0); 

% CAR3 is made from the "corner" portfolios
car3 = (resCAR3.pret(:,3) + resCAR3.pret(:,6) - ...
         (resCAR3.pret(:,1) + resCAR3.pret(:,4)) )/2;   

% Match the time period
s = find(dates==197501);
e = find(dates==201212);

% Table 2, column 1
prt(nanols(umd(s:e),[const(s:e) mkt(s:e) smb(s:e) hml(s:e)]))

% Table 2, column 3
prt(nanols(umd(s:e),[const(s:e) mkt(s:e) smb(s:e) hml(s:e) sue(s:e) car3(s:e)]))


%% Trading cost taxonomy from Novy-Marx and Velikov (2016)

% Load some variables
clear
clc

load dates
load me
load ret
load NYSE
load gibbs_filled

% Read in the 23 anomalies
[anoms23, labels23] = getAnomalySignals('novyMarxVelikovAnomalies.csv', 1, 2);

% Store the number of anomalies
nAnoms = size(anoms23, 3);

% Get the starting dates. These are hard-coded here - bad old habits.
startDate = [1 1 1 1 1 1 1 1 2 2 2 1 1 1 1 2 2 1 1 1 1 1 1]; % 1 - 196306, 2 - 197306
startDate(startDate==1) = max(196306, dates(1));
startDate(startDate==2) = max(197306, dates(1));


% Loop through the anomalies
for i = 1:nAnoms
    % Run a univariate sort for each (value-weighted, decile-sort, NYSE breaks)
    sortVar = anoms23(:, :, i);
    ind = makeUnivSortInd(sortVar, 10, NYSE);
    ind = 1 * (ind==1) + ...
          2 * (ind==10);
    res = runUnivSort(ret, ind, dates, me, 'tcosts', tcosts, ...
                                           'timePeriod', [startDate(i) 201212], ...
                                           'plotFigure', 0, ...
                                           'printResults', 0); 

    % Store the results
    coefs(i,:) = [res.xret(end) res.alpha(end) res.turnover 100*res.tcosts res.netxret];
    tstats(i,:) = [res.txret(end) res.talpha(end) nan nan res.tnetxret];
end

% Print latex-style output
mat2Tex(coefs, tstats, labels23, 2)

%% Combination strategy  - LASSO

% Load some variables
clear
clc

load dates
load me
load ret
load NYSE
load tcosts

% Determine the time period
timePeriod = [198001 202112];

% Read in the 23 anomalies
[anoms23, labels23] = getAnomalySignals('novyMarxVelikovAnomalies.csv', 1, 2);

% Check & fill them in
[filledAnoms, keepAnoms, keepRollAnoms] = checkFillAnomalies(anoms23, me, dates, timePeriod);

% Get the expected return signal
expRet = makeLassoRes(filledAnoms(:,:,keepAnoms), ret, dates, timePeriod);

% Let's sort and see how a decile, value-weighted, NYSE-breaks strategy does
ind = makeUnivSortInd(expRet, 10, NYSE);
resVW = runUnivSort(ret, ind, dates, me, 'weighting', 'v', ...
                                         'factorModel', 6, ...
                                         'tcosts', tcosts, ...
                                         'plotFigure', 0); 

% Run an equal-weighted one to compare
resEW = runUnivSort(ret, ind, dates, me, 'weighting' , 'e', ...
                                         'factorModel', 6, ...
                                         'tcosts', tcosts, ...
                                         'plotFigure', 0); 

% Compare the performance of these strategies with and without trading
% costs
figure;
rets = [resVW.pret(:,end) resVW.netpret ...
        resEW.pret(:,end) resEW.netpret];
ibbots(rets, dates, 'timePeriod', 199001, ...
                    'legendLabels', {'VWgross','VWnet','EWgross','EWnet'});


%% Anomaly decay results (McLean and Pontiff, 2016; Chen and Velikov, 2022)

% Load some variables
clear
clc

load dates
load ret
load tcosts
load NYSE
load prc
load exchcd
load me

% Timekeeping
fprintf('Start at %s.\n',char(datetime('now')));
tic;

% Read the Chen and Zimmerman anomalies
[anoms, labels, anomaly_summary] = getChenZimmermanAnomalies();

% Store a few monthly indicators
mths = dates - 100*floor(dates/100);
JuneIndicator         = (mths==6);
JuneDecemberIndicator = (mths==6 | mths==12);
quarterEndIndicator   = (mths==3 | mths==6 | mths==9 | mths==12);

% Store some dimensions
[nMonths, nStocks, nAnoms] = size(anoms);

% Loop through the anomalies
for i=1:nAnoms
    
    % Store the current anomaly
    var = anoms(:,:,i);
        
    % Finds the row in the summary file
    r = find(strcmp(anomaly_summary.Acronym, labels(i)));
    
    % Figure out the rebalancing period
    if anomaly_summary.PortfolioPeriod(r) == 12 || ...
       anomaly_summary.PortfolioPeriod(r) == 36
        var(~JuneIndicator,:) = nan;
    elseif anomaly_summary.PortfolioPeriod(r) == 6
        var(~JuneDecemberIndicator,:) = nan;
    elseif anomaly_summary.PortfolioPeriod(r) == 3
        var(~quarterEndIndicator,:) = nan;
    end
        
    % Check for potential filters
    if ~strcmp(anomaly_summary.Filter(r), '')
        filterString = regexprep(anomaly_summary.Filter(r), ' ', '');
        if contains(filterString, 'abs(prc)>1')
            var(abs(prc)<=1) = nan;  
        end
        if contains(filterString, 'abs(prc)>5')
            var(abs(prc)<=5) = nan;  
        end
        if contains(filterString, 'exchcd%in%c(1,2)')
            var(exchcd>2) = nan;
        end
        if contains(filterString, 'exchcd==1')
            var(exchcd>1) = nan;
        end
        if contains(filterString, 'me>me_nyse20')
            indME5 = makeUnivSortInd(me, 5, NYSE);
            var(indME5==1) = nan;
        end
    end
                        
    % Determine the sample
    if isnan(anomaly_summary.StartMonth(r))
        sampleStart = 100*anomaly_summary.SampleStartYear(r) + 6;    
    else
        sampleStart = 100*anomaly_summary.SampleStartYear(r) + anomaly_summary.StartMonth(r);
    end
    lastHoldDate = find(sum(isfinite(var),2)>0,1,'last') + anomaly_summary.PortfolioPeriod(r);
    sampleEnd = dates(min(lastHoldDate, nMonths));
    dts = [sampleStart sampleEnd];
    
    % Determine the number of portfolios
    if strcmp(anomaly_summary.Acronym(r), 'ChangeInRecommendation')
        bpts = prctile(var,[20 80],2);        
        ind = 1 * (var<=repmat(bpts(:,1), 1, nStocks)) + ...
              2 * (var>=repmat(bpts(:,2), 1, nStocks));        
    elseif ismember(anomaly_summary.Acronym(r), {'NumEarnIncrease','RDcap'})
        ind = 1 * (var==0) + ...
              2 * (var>0);
    elseif strcmp(anomaly_summary.Cat_Form(r), 'discrete')       
        uVals = unique(var);
        uVals(isnan(uVals)) = [];
        ind = 1 * (var==min(uVals)) + ...
              2 * (var==max(uVals));
    else
        if isnan(anomaly_summary.LSQuantile(r))
            nptfs = 5;
        else
            nptfs = round(1/anomaly_summary.LSQuantile(r));
        end
        ind = makeUnivSortInd(var,nptfs);  
        if strcmp(anomaly_summary.QuantileFilter(r),'NYSE')
            ind = makeUnivSortInd(var,nptfs,NYSE);  
        end
        ind = 1 * (ind==1) + ...
              2 * (ind==nptfs);
    end

    % Run the univariate regression
    if strcmp(anomaly_summary.StockWeight(i), 'VW')
        res(i,1) = runUnivSort(ret, ind, dates, me, 'weighting', 'v', ...
                                                    'timePeriod', dts, ...
                                                    'plotFigure', 0, ...
                                                    'printResults', 0);  
    else
        res(i,1) = runUnivSort(ret, ind, dates, me, 'weighting', 'e', ...
                                                    'timePeriod', dts, ...
                                                    'plotFigure', 0, ...
                                                    'printResults', 0);      
    end
end

% Timekeeping
fprintf('Done running sorts at at %s.\n', char(datetime('now')));
% Check how much memory is used
memory

% Make anomaly returns relative to publication
relativeRets    = nan(2*nMonths+1, nAnoms);

% Loop through the anomalies
for i=1:nAnoms
    % Find the row for this anomaly in the summary table
    r = find(strcmp(anomaly_summary.Acronym,labels(i)));

    % Store the publication date (assume December)
    pubDate = 100*anomaly_summary.Year(r) + 12;

    % Find the publication date in the univariate sort structure
    e = find(res(i).dates==pubDate);

    % Store the returns in the relative returns matrix
    prePubInd = nMonths-e+1:nMonths;
    relativeRets(prePubInd,i) = res(i).pret(1:e,end);
    
    postPubInd = (nMonths+1):(nMonths+length(res(i).dates)-e);
    relativeRets(postPubInd,i) = res(i).pret(e+1:end,end);    
end

% Now let's plot the figure
figure;
x = (-nMonths:nMonths)/12;
y = 100 * mean(relativeRets, 2, 'omitnan');
plot(x, y, 'Color', [0.8 0.8 0.8]);
hold on;
smoothY = 100 * moving(mean(relativeRets, 2, 'omitnan'), 60);
plot(x, smoothY);
ylim([-0.5 1]);
xlim([-30 20]);
xlabel('Years relative to publication');
title('Average returns across anomalies');
legend('Average','5-year moving average');

% Timekeeping
toc;

%% Data download

% Let's get Tesla's daily stock returns and accounting information 
clear
clc

% Input your WRDS username
Params.username = usernameUI();                                            

% Input your WRDS password
Params.pass     = passwordUI();                                            

% Call WRDS connection
WRDS = callWRDSConnection(Params.username,Params.pass);

% Download Tesla's stock price
ticker = 'TSLA';
qry = ['select date, prc from CRSP.DSF left join CRSP.DSFHDR on dsf.permno=dsfhdr.permno where htick=''', ticker, ''''];
prcTable = fetch(WRDS, qry);

% Convert the dates to a datetime & sort
prcTable.date = datetime(prcTable.date);
prcTable = sortrows(prcTable,'date');

% Plot the price
figure;
plot(prcTable.date,prcTable.prc);

% Now let's get the cumulative factor to adjust price
qry = ['select date, prc, cfacpr from CRSP.DSF left join CRSP.DSFHDR on dsf.permno=dsfhdr.permno where htick=''', ticker, ''''];
newPrcTable = fetch(WRDS, qry);

% Convert the dates to a datetime & sort
newPrcTable.date = datetime(newPrcTable.date);
newPrcTable = sortrows(newPrcTable,'date');

% Calculate the adjusted price
newPrcTable.adjPrc = newPrcTable.prc ./ newPrcTable.cfacpr;

% Plot the adjusted price
hold on;
plot(newPrcTable.date, newPrcTable.adjPrc);
legend('Raw price','Adjusted price');
hold off;

% Now let's get Tesla's quarterly revenue and assets:
qry = ['select fdateq, rdq, atq, revtq from COMP.FUNDQ where tic=''', ticker, ''''];
acctTable = fetch(WRDS, qry);

% Convert the dates
acctTable.fdateq = datetime(acctTable.fdateq);
acctTable.rdq = datetime(acctTable.rdq);

% Plot their assets against the fiscal quarter end dates
plot(acctTable.fdateq, acctTable.atq/1000);
ylabel('Quarterly total assets ($ bln)');

% Plot their revenues against the fiscal quarter end dates
plot(acctTable.fdateq, acctTable.revtq);
ylabel('Quarterly total assets ($ mln)');
