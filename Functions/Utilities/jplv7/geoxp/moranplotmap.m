function [out1,out2]=moranplotmap(long,lat,variable,mat,flower,varargin)
% PURPOSE: This function links a map and a moran scatterplot
%------------------------------------------------------------------------
% USAGE: [out1,out2]=moranplotmap(long,lat,variable,mat,flower,carte,label,symbol)
%   where : 
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           variable = n x 1 vector of the variable to study
%           mat = weight matrix
%           flower = flower = 1 : link selected points with their neighbors.
%                    flower =0 : don't link selected points with their neighbors.   
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out1 = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%          out2 = stardard moran index
%------------------------------------------------------------------------
% MANUAL: Select points on either the map or the scatterplot by clicking with the left mouse button
%         You can select points inside a polygon: - right click to set the first point of the polygon
%                                                 - left click to set the other points
%                                                 - right click to close the polygon
%         You can select whole quadrants: - push 1 to select the first quadrant
%                                         - push 2 to select the second quadrant
%                                         - push 3 to select the third quadrant
%                                         - push 4 to select the fourth quadrant
%         Selection is lost when you switch graph or selection mode (quadrant vs point)
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr



close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
c=0;
l=0;
symbol=0;
vectx=[];
vecty=[];
name=inputname(3);
variable=variable-mean(variable); % centered variable
L=sparse(length(lat),length(lat));
%creation of a menu to save
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save moranfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%

% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        carte=varargin{1};
        c=1;
    end;
    if  t>=2 & ~isempty(varargin{2})
        label=varargin{2};
        l=1;
    end;
    if t==3 & ~isempty(varargin{3})
        symbol=varargin{3};
    end;
end;
%%%%%%%%%%%%%%%%%%%%%

% Trace the map
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');
%%%%%%%%%%%%%%%%%%%%%
[I,J]=find(mat~=0);
WX=mat*variable;
stdvar=variable/std(variable,1); 
%Iloc=Ilocal(variable,mat);
Iloc=Ilocal(stdvar,mat);
Iloc=Iloc';
%Imoran=Idemoran(variable,mat);
const=ones(length(variable),1);
res=nonormmoran(stdvar,const,mat);
Imoran=[res.morani];
pvalue=1-norm_cdf(Imoran,0,1);
Ht=uicontrol('Style','text','String',['Moran index:',num2str(Imoran)],'Position',[820,20,180,20],'Enable','inactive');
set(Ht,'Units','normalized');
set(Ht,'Position',[0.64,0.025,0.14,0.025]);
Ht2=uicontrol('Style','text','String',['p-value:',num2str(pvalue)],'Position',[620,20,180,20],'Enable','inactive');
set(Ht2,'Units','normalized');
set(Ht2,'Position',[0.49,0.025,0.14,0.025]);
% Trace the moran scatter plot
Axis2=subplot(1,2,2);
plot(variable,WX,'b.');
title('moran scatter Plot');
xlabel(name);
axis square;
hold on;
line([0 0],[max(WX) min(WX)],'Color','black');
line([max(variable) min(variable)],[0 0],'Color','black');
axis manual;
subplot(Axis1);
axis manual;

Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');
%%%%%%%%%%%%%%%%%%%%%

% create the buttons
q1=uicontrol('Style','togglebutton','string','Quadrant 1','BackGroundColor',[0.8 0.5 0],'Enable','inactive');
set(q1,'Units','normalized');
set(q1,'position',[0.015,0.025,0.05,0.026]);
q2=uicontrol('Style','togglebutton','string','Quadrant 2','BackGroundColor',[0.5 0.8 0],'Position',[100 20 60 20],'Enable','inactive');
set(q2,'Units','normalized');
set(q2,'Position',[0.078,0.025,0.05,0.026]);
q3=uicontrol('Style','togglebutton','string','Quadrant 3','BackGroundColor',[1 0.8 0.5],'Position',[180 20 60 20],'Enable','inactive');
set(q3,'Units','normalized');
set(q3,'Position',[0.14,0.025,0.05,0.026]);
q4=uicontrol('Style','togglebutton','string','Quadrant 4','BackGroundColor',[1 0.2 0.8],'Position',[260 20 60 20],'Enable','inactive');
set(q4,'Units','normalized');
set(q4,'Position',[0.20,0.025,0.047,0.025]);

%%%%%%%%%%%%%%%%%%%

% define the quadrants
Q1=find(variable>0 & WX>0);
Q2=find(WX>0 & variable<0);
Q3=find(WX<0 & variable<0);
Q4=find(variable>0 & WX<0);
%%%%%%%%%%%%%%%%%%%%%%%

% Main loop
maptest=0;
morantest=0;
BUTTON=0;
affq1=0;
affq2=0;
affq3=3;
affq4=4;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    %redraw the graphs
    subplot(Axis2);
    hold on;
    cla;
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    [LIselect,LJselect]=find(L==1);
    reg=ols(WX,variable);
    line([0 0],[max(WX) min(WX)],'Color','black');
    line([max(variable) min(variable)],[0 0],'Color','black');
    plot(variable,reg.beta*variable,'y')
    if ~isempty(Iunselect)
      plot(variable(Iunselect),WX(Iunselect),'b.');
    end;
    if affq1==1
        if symbol==1
            plot(variable(Q1),WX(Q1),'o','color',[0 0 1]);
        else
            plot(variable(Q1),WX(Q1),'.','color',[0.8 0.5 0]);
        end;
    end;
    if affq2==1
        if symbol==1
            plot(variable(Q2),WX(Q2),'*','color',[0 0 1]);
        else
            plot(variable(Q2),WX(Q2),'.','color',[0.5 0.8 0]);
        end;
    end;
    if affq3==1
        if symbol==1
            plot(variable(Q3),WX(Q3),'d','color',[0 0 1]);
        else
            plot(variable(Q3),WX(Q3),'.','color',[1 0.8 0.2]);
        end;
    end;
    if affq4==1
        if symbol==1
            plot(variable(Q4),WX(Q4),'h','color',[0 0 1]);
        else
            plot(variable(Q4),WX(Q4),'.','color',[1 0.2 0.8]);
        end;
    end;
    if ~isempty(Iselect) & BUTTON~=49 & BUTTON~=50 & BUTTON~=51 & BUTTON~=52
        if maptest==1
            if symbol==1
                plot(variable(Iselect),WX(Iselect),'b*');
            else
                plot(variable(Iselect),WX(Iselect),'r.');
            end;
            Htex=text(variable(Iselect),WX(Iselect),num2str(Iloc(Iselect)'));
            set(Htex,'FontSize',8);
        elseif morantest==1
            if symbol==1
                plot(variable(Iselect),WX(Iselect),'bo');
            else
                plot(variable(Iselect),WX(Iselect),'m.'); 
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
            Htex=text(variable(Iselect),WX(Iselect),num2str(Iloc(Iselect)'));
            set(Htex,'FontSize',8);
        end;
    end;
    
    
    hold off;
    subplot(Axis1);
    hold on;
    cla;
    
    if c==1
        plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect)
      plot(long(Iunselect),lat(Iunselect),'b.');
    end;
    if affq1==1
        if ~isempty(Q1) & get(q1,'Value')==1
            if symbol==1
                plot(long(Q1),lat(Q1),'o','color',[0 0 1]);
            else
                plot(long(Q1),lat(Q1),'.','color',[0.8 0.5 0]);
            end;
            if l==1
                Htex=text(long(Q1),lat(Q1),num2str(label(Q1)));
                set(Htex,'FontSize',8);
            end;
        end;
    end;
    if affq2==1
        if ~isempty(Q2) & get(q2,'Value')==1
            if symbol==1
                plot(long(Q2),lat(Q2),'*','color',[0 0 1]);
            else
                plot(long(Q2),lat(Q2),'.','color',[0.5 0.8 0]);
            end;
            if l==1
                Htex=text(long(Q2),lat(Q2),num2str(label(Q2)));
                set(Htex,'FontSize',8);
            end;
        end;
    end;
    if affq3==1
        if ~isempty(Q3) & get(q3,'Value')==1
            if symbol==1
                plot(long(Q3),lat(Q3),'d','color',[0 0 1]);
            else
                plot(long(Q3),lat(Q3),'.','color',[1 0.8 0.2]);
            end;
            if l==1
                Htex=text(long(Q3),lat(Q3),num2str(label(Q3)));
                set(Htex,'FontSize',8);
            end;
        end;
    end;
    if affq4==1
        if ~isempty(Q4) & get(q4,'Value')==1
            if symbol==1
                plot(long(Q4),lat(Q4),'h','color',[0 0 1]);
            else
                plot(long(Q4),lat(Q4),'.','color',[1 0.2 0.8]);
            end;
            if l==1
                Htex=text(long(Q4),lat(Q4),num2str(label(Q4)));
                set(Htex,'FontSize',8);
            end;
        end;
    end;
    if ~isempty(Iselect) & BUTTON~=49 & BUTTON~=50 & BUTTON~=51 & BUTTON~=52
        if maptest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'b*');  
            else
                plot(long(Iselect),lat(Iselect),'r.');      
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif morantest==1
            if flower==1
                if symbol==1
                    plot(long(LIselect),lat(LIselect),'bd');
                else
                    plot(long(LIselect),lat(LIselect),'g.');
                end;
            end;
            if symbol==1
                plot(long(Iselect),lat(Iselect),'bo');  
            else
                plot(long(Iselect),lat(Iselect),'m.');      
            end;       
        end;
        if flower==1
            [LIselect,LJselect]=find(triu(L)==1);
            ligne=line([long(LIselect)' ;long(LJselect)'],[lat(LIselect)'; lat(LJselect)']);
            set(ligne,'Color','black');
        end;
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
    if (BUTTON==49 | BUTTON==50 | BUTTON==51 | BUTTON==52) & affq1==0 & affq2==0 & affq3==0 & affq4==0
        obs=zeros(size(long,1),1);
        maptest=0;
        morantest=0;
        L=sparse(length(lat),length(lat));
    end;
    % quadrant selection
    if BUTTON==49 | BUTTON==50 | BUTTON==51 | BUTTON==52
        maptest=0;
        morantest=0;
        [obs,affq1,affq2,affq3,affq4]=selectstat('moran',obs,variable,'quadrant',BUTTON,q1,q2,q3,q4,Q1,Q2,Q3,Q4,affq1,affq2,affq3,affq4);
    %%%%%%%%%%%%%%%%%%%%
    % map selection
    elseif (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        if maptest==0
            maptest=1;
            morantest=0;
            L=sparse(length(lat),length(lat));
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2  & BUTTON~=49 & BUTTON~=50 & BUTTON~=51 & BUTTON~=52
            if affq1==1 | affq2==1 | affq3==1 | affq4==1
                obs=zeros(size(long,1),1);
                set(q1,'Value',0);
                set(q2,'Value',0);
                set(q3,'Value',0);
                set(q4,'Value',0);
                affq1=0;
                affq2=0;
                affq3=0;
                affq4=0;
            end;
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'point');   
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            if affq1==1 | affq2==1 | affq3==1 | affq4==1
                obs=zeros(size(long,1),1);
                set(q1,'Value',0);
                set(q2,'Value',0);
                set(q3,'Value',0);
                set(q4,'Value',0);
                affq1=0;
                affq2=0;
                affq3=0;
                affq4=0;
            end;
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'poly');
        
        end;
        %%%%%%%%%%%%%%%%%%%
    %%%%%%%%%%%%%%%%%%%%%%%
    % moranplot selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        if morantest==0
            morantest=1;
            maptest=0;
            obs=zeros(size(long,1),1);
            L=sparse(length(lat),length(lat));
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2  & BUTTON~=49 & BUTTON~=50 & BUTTON~=51 & BUTTON~=52
            if affq1==1 | affq2==1 | affq3==1 | affq4==1
                obs=zeros(size(long,1),1);
                set(q1,'Value',0);
                set(q2,'Value',0);
                set(q3,'Value',0);
                set(q4,'Value',0);
                affq1=0;
                affq2=0;
                affq3=0;
                affq4=0;
            end;
            [obs,L]=selectstat('moran',obs,variable,'point',WX,x,y,L,mat);
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            if affq1==1 | affq2==1 | affq3==1 | affq4==1
                obs=zeros(size(long,1),1);
                set(q1,'Value',0);
                set(q2,'Value',0);
                set(q3,'Value',0);
                set(q4,'Value',0);
                affq1=0;
                affq2=0;
                affq3=0;
                affq4=0;
            end;
            [obs,vectx,vecty,L]=selectstat('moran',obs,variable,'poly',WX,x,y,L,mat);     
        end;
        %%%%%%%%%%%%%%%%%%%%
    end;
    %%%%%%%%%%%%%%%%%%%%%%
end;
out1=obs;
out2=Imoran;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%